from flask import Flask
from routes.deploy import deploy_bp

app = Flask(__name__)

# Регистрируем Blueprint для деплоя
app.register_blueprint(deploy_bp)

# Можно добавить другие Blueprint'ы позже (api_bp, auth_bp, etc.)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8080)