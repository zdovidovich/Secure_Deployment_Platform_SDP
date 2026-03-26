from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy():
    return "В разработке" 
# проверка загруженных параметров

if __name__ == '__main__':
  app.run(debug=True, port=8080)