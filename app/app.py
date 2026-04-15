from flask import Flask, redirect
from routes import api_bp, web_bp

app = Flask(__name__)

app.register_blueprint(web_bp)
app.register_blueprint(api_bp)

@app.route('/')
def index():
    return redirect('/deploy/', 301)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)
