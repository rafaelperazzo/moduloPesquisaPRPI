#
# Conteudo do arquivo `myapp.py`
#
from flask import Flask
from flask import render_template
from flask import request,url_for,send_file,send_from_directory
from modules import dec

app = Flask(__name__)

@app.route("/")
def home():
    return render_template('a4.html')

#@app.route("/minhadeclaracao", methods=['GET', 'POST'])
#def mydec():
#    return render_template('a4.html')

@app.route("/consulta")
def consulta():
    return render_template('_consulta.html')

@app.route("/declaracao", methods=['GET', 'POST'])
def declaracao():
    pdf_path = dec.gerarDeclaracao(str(request.form['txtCPF']))
    return render_template('a4.html',texto=pdf_path)
    #return send_from_directory(pdf_path, str(request.form['txtCPF']) + '.pdf')
    #return("OK")


if __name__ == "__main__":
    app.run()
