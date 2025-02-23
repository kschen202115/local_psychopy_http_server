from flask import Flask, render_template_string, send_from_directory
import os

app = Flask(__name__)

def get_files():
    """
    Returns a list of files in the current directory.
    """
    return [f for f in os.listdir('./') if os.path.isfile(f)]

@app.route('/<id>/')
def index(id):
    files = get_files()
    file_list = "<br>".join([f'<a href="/{id}/{f}">{f}</a>' for f in files])  # Corrected the href
    return render_template_string("""
        <h1>文件列表</h1>
        <p>{{ file_list | safe }}</p>
    """, file_list=file_list)

@app.route('/<id>/<path:filename>')
def serve_static(filename, id):
    return send_from_directory('./', filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=45678, debug=True)
