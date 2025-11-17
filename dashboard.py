from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)

# Pour simplifier, pas de système de login complexe ici.
# Dans un vrai projet, il faudrait un système d'authentification sécurisé (ex: Flask-Login).
ADMIN_PASSWORD = "motdepassesupersecret" 

def get_db_connection():
    conn = sqlite3.connect('gendarmerie.db')
    conn.row_factory = sqlite3.Row # Permet d'accéder aux colonnes par leur nom
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    casiers = conn.execute('SELECT * FROM casiers ORDER BY id DESC').fetchall()
    gendarmes = conn.execute('SELECT * FROM gendarmes').fetchall()
    conn.close()
    return render_template('index.html', casiers=casiers, gendarmes=gendarmes)

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Ceci est une sécurité très basique, à ne PAS utiliser en production !
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            # Dans une vraie app, on utiliserait une session
            return redirect(url_for('index'))
        else:
            return "Mot de passe incorrect", 403
    return render_template('login.html')

# --- Pour que Flask puisse afficher les pages, il faut des fichiers HTML ---
# Crée un dossier "templates" à côté de `dashboard.py`
# et dedans, crée `index.html` et `login.html`.

if __name__ == '__main__':
    # Pour l'hébergement sur ton serveur, tu devras configurer un serveur de production (Gunicorn, Nginx).
    # Le `host='0.0.0.0'` permet d'accéder au site depuis l'extérieur de la machine.
    app.run(host='0.0.0.0', port=30137, debug=True)
