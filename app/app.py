from flask import Flask, redirect, url_for
from routes.deploy import deploy_bp

app = Flask(__name__)

app.register_blueprint(deploy_bp)

@app.route('/')
def index():
    return redirect('deploy', 301)

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8080)