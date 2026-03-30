# app/routes/deploy.py
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, Response
import uuid
import threading
import time
import json

from sse.broadcaster import SSEBroadcaster
from services.deployment import DeploymentService

# Создаём Blueprint для группы маршрутов
deploy_bp = Blueprint('deploy', __name__, url_prefix='/deploy')

# Хранилище активных задач: { session_id: DeploymentService }
active_deployments = {}


@deploy_bp.route('/', methods=['GET'])
def index():
    """Главная страница с формой"""
    return render_template('index.html')


@deploy_bp.route('/', methods=['POST'])
def start_deployment():
    """
    Запуск деплоя.
    1. Валидация ввода
    2. Создание сессии
    3. Запуск в фоне
    4. Редирект на страницу статуса
    """
    # Быстрая проверка файлов
    if not request.files.get('ssh_key') or not request.files.get('docker_image'):
        return jsonify({"error": "Требуется загрузка SSH-ключа и Docker-образа"}), 400
    
    # ИЗВЛЕКАЕМ ДАННЫЕ В ГЛАВНОМ ПОТОКЕ (пока контекст запроса активен)
    form_data = request.form.to_dict()
    
    # Сохраняем файлы во временную папку СРАЗУ, чтобы поток мог их прочитать
    from libs.temp_files import save_temp_file
    file_paths = {
        'ssh_key': save_temp_file(request.files.get('ssh_key'), "ssh_key_"),
        'docker_image': save_temp_file(request.files.get('docker_image'), "docker_image_"),
    }
    
    # Dockerfile опционально
    if request.files.get('dockerfile') and request.files['dockerfile'].filename:
        file_paths['dockerfile'] = save_temp_file(request.files['dockerfile'], "dockerfile_")
    
    # Создаём уникальную сессию
    session_id = uuid.uuid4().hex[:12]
    
    # Создаём сервис деплоя
    service = DeploymentService(session_id)
    active_deployments[session_id] = service
    
    # Запускаем в фоновом потоке, передавая ДАННЫЕ, а не request объекты
    def run_in_background():
        try:
            service.execute(form_data, file_paths)
        except Exception as e:
            service.status = "error"
            service.result = {"error": f"Critical error: {str(e)}"}
            service.logger.error(f"Critical error: {str(e)}")
    
    thread = threading.Thread(target=run_in_background)
    thread.daemon = True  # Поток завершится при остановке приложения
    thread.start()
    
    # Редирект на страницу статуса
    return redirect(url_for('deploy.status', session_id=session_id))


@deploy_bp.route('/status/<session_id>')
def status(session_id: str):
    """Страница статуса деплоя (с консолью)"""
    if session_id not in active_deployments:
        return render_template('deploy_not_found.html', session_id=session_id), 404
    
    service = active_deployments[session_id]
    return render_template('deploy_status.html', session_id=session_id, status=service.status)


@deploy_bp.route('/stream/<session_id>')
def stream(session_id: str):
    """
    SSE-эндпоинт: передаёт логи в реальном времени.
    Браузер подключается через EventSource.
    """
    def generate():
        last_index = 0
        while True:
            # Получаем новые события
            events = SSEBroadcaster.get_events(session_id, last_index)
            
            for event in events:
                # Формат SSE: "data: {...}\n\n"
                yield f"data: {json.dumps(event)}\n\n" 
                last_index += 1
            
            # Проверяем, завершён ли деплой
            if session_id in active_deployments:
                service = active_deployments[session_id]
                if service.status in ['success', 'error']:
                    # Отправляем финальное событие
                    yield f"data: {json.dumps({'type': 'finished', 'status': service.status})}\n\n"
                    # Очищаем сессию через 5 секунд
                    time.sleep(5)
                    SSEBroadcaster.cleanup_session(session_id)
                    del active_deployments[session_id]
                    break
            else:
                # Сессия уже удалена
                break
            
            time.sleep(0.5)  # Пауза между опросами
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'  # Для Nginx
        }
    )


@deploy_bp.route('/api/status/<session_id>')
def api_status(session_id: str):
    """API-эндпоинт для получения статуса (JSON)"""
    if session_id not in active_deployments:
        return jsonify({"error": "Session not found"}), 404
    
    service = active_deployments[session_id]
    return jsonify({
        "session_id": session_id,
        "status": service.status,
        "result": service.result
    })