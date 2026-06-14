import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

raiz_do_projeto = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

app = Flask(
    __name__,
    template_folder=os.path.join(raiz_do_projeto, 'templates'),
    static_folder=os.path.join(raiz_do_projeto, 'static')
)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.abspath(os.path.join(os.path.dirname(__file__), 'database', 'database.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)

@app.route('/')
def home():
    return render_template('index.html')

@app.route("/cadastro", methods=['GET', 'POST'])
def cadastro_route():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        
        if name and email:
            try:
                novo_usuario = Usuario(name=name, email=email)
                db.session.add(novo_usuario)
                db.session.commit()
                return "<p>Cadastro recebido com sucesso!</p>"
            except Exception as e:
                db.session.rollback()
                return "<p>Erro: Este e-mail já está cadastrado ou ocorreu um problema.</p>", 400
        
        return "<p>Por favor, preencha todos os campos!</p>", 400

    return redirect(url_for('home'))

if __name__ == '__main__':
    pasta_database = os.path.abspath(os.path.join(os.path.dirname(__file__), 'database'))
    os.makedirs(pasta_database, exist_ok=True)
    
    with app.app_context():
        db.create_all()
        
    app.run(debug=True)