import json
import os
import threading
import time

from flask import Blueprint, Response, jsonify, request

from libs.temp_files import save_temp_file
from services.deployment_store import deployment_store
from sse.broadcaster import SSEBroadcaster

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _check_api_key():
    configured_api_key = os.getenv("SDP_API_KEY")
    if not configured_api_key:
        return None

    request_api_key = request.headers.get("X-API-Key")
    if request_api_key == configured_api_key:
        return None

    return jsonify({"error": "Unauthorized"}), 401


def _build_file_paths():
    file_paths = {
        "ssh_key": save_temp_file(request.files.get("ssh_key"), "ssh_key_"),
        "docker_image": save_temp_file(
            request.files.get("docker_image"), "docker_image_"
        ),
    }

    if request.files.get("dockerfile") and request.files["dockerfile"].filename:
        file_paths["dockerfile"] = save_temp_file(
            request.files["dockerfile"], "dockerfile_"
        )

    return file_paths


@api_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@api_bp.route("/deployments", methods=["POST"])
def create_deployment():
    auth_error = _check_api_key()
    if auth_error:
        return auth_error

    if not request.files.get("ssh_key") or not request.files.get("docker_image"):
        return (
            jsonify(
                {
                    "error": "Both files are required",
                    "required_files": ["ssh_key", "docker_image"],
                }
            ),
            400,
        )

    form_data = request.form.to_dict()
    file_paths = _build_file_paths()
    job = deployment_store.create()

    def run_in_background():
        try:
            job.service.execute(form_data, file_paths)
        except Exception as exc:
            job.service.status = "error"
            job.service.result = {"error": f"Critical error: {str(exc)}"}
            job.service.logger.error(f"Critical error: {str(exc)}")

    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()

    return (
        jsonify(
            {
                "deployment_id": job.deployment_id,
                "status": job.service.status,
                "created_at": job.created_at,
                "status_url": f"/api/v1/deployments/{job.deployment_id}",
                "events_url": f"/api/v1/deployments/{job.deployment_id}/events",
                "web_url": f"/deploy/status/{job.deployment_id}",
            }
        ),
        202,
    )


@api_bp.route("/deployments/<deployment_id>", methods=["GET"])
def get_deployment(deployment_id: str):
    auth_error = _check_api_key()
    if auth_error:
        return auth_error

    job = deployment_store.get(deployment_id)
    if not job:
        return jsonify({"error": "Deployment not found"}), 404

    return jsonify(
        {
            "deployment_id": deployment_id,
            "created_at": job.created_at,
            "status": job.service.status,
            "result": job.service.result,
        }
    )


@api_bp.route("/deployments/<deployment_id>/events", methods=["GET"])
def stream_deployment(deployment_id: str):
    auth_error = _check_api_key()
    if auth_error:
        return auth_error

    job = deployment_store.get(deployment_id)
    if not job:
        return jsonify({"error": "Deployment not found"}), 404

    def generate():
        last_index = 0
        while True:
            events = SSEBroadcaster.get_events(deployment_id, last_index)

            for event in events:
                yield f"data: {json.dumps(event)}\n\n"
                last_index += 1

            current_job = deployment_store.get(deployment_id)
            if not current_job:
                break

            if current_job.service.status in ["success", "error"]:
                yield (
                    f"data: {json.dumps({'type': 'finished', 'status': current_job.service.status})}\n\n"
                )
                time.sleep(5)
                SSEBroadcaster.cleanup_session(deployment_id)
                deployment_store.remove(deployment_id)
                break

            time.sleep(0.5)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
