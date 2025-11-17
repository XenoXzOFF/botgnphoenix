import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from datetime import datetime
import threading
from flask import Flask, render_template, request, redirect, url_for
import asyncio
from flask import session, flash

# --- Configuration ---
# Remplace par ton vrai token dans un fichier de configuration ou une variable d'environnement
# Ne jamais écrire le token directement dans le code !
BOT_TOKEN = "TON_TOKEN_DISCORD_ICI" 
GUILD_ID = 123456789012345678 # ID de ton serveur Discord (clic droit sur le serveur > Copier l'ID)

# --- Configuration du Dashboard Web ---
app = Flask(__name__)
app.secret_key = os.urandom(24) # Clé secrète pour la gestion des sessions

# Pour simplifier, pas de système de login complexe ici.
# Dans un vrai projet, il faudrait un système d'authentification sécurisé (ex: Flask-Login).
ADMIN_PASSWORD = "motdepassesupersecret" 

def get_db_connection():
    conn = sqlite3.connect('gendarmerie.db')
    conn.row_factory = sqlite3.Row # Permet d'accéder aux colonnes par leur nom
    return conn

@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    casiers = conn.execute('SELECT * FROM casiers ORDER BY id DESC').fetchall()
    gendarmes = conn.execute('SELECT * FROM gendarmes').fetchall()
    conn.close()
    return render_template('index.html', casiers=casiers, gendarmes=gendarmes)

@app.route('/config', methods=['GET', 'POST'])
@login_required
def config():
    conn = get_db_connection()
    if request.method == 'POST':
        # Enregistre les nouvelles valeurs
        gendarme_role_id = request.form.get('gendarme_role_id')
        casier_log_channel_id = request.form.get('casier_log_channel_id')
        
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('gendarme_role_id', gendarme_role_id))
        cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('casier_log_channel_id', casier_log_channel_id))
        conn.commit()
        flash("Configuration enregistrée avec succès !", "success")
        return redirect(url_for('config'))

    # Affiche les valeurs actuelles
    config_data = {row['key']: row['value'] for row in conn.execute('SELECT * FROM config').fetchall()}
    conn.close()
    return render_template('config.html', config=config_data)

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Ceci est une sécurité très basique, à ne PAS utiliser en production !
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash("Connexion réussie !", "success")
            return redirect(url_for('index'))
        else:
            flash("Mot de passe incorrect.", "danger")
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for('login'))

# --- Initialisation de la base de données ---
def init_db():
    conn = sqlite3.connect('gendarmerie.db')
    cursor = conn.cursor()
    
    # Table pour les casiers judiciaires
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS casiers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prenom TEXT NOT NULL,
        nom TEXT NOT NULL,
        age INTEGER,
        date_naissance TEXT,
        telephone TEXT,
        profession TEXT,
        date_faits TEXT NOT NULL,
        infractions TEXT NOT NULL,
        statut_judiciaire TEXT DEFAULT 'En cours',
        appel_status TEXT DEFAULT 'Aucun' -- 'Aucun', 'En attente', 'Accepté', 'Refusé'
    )
    ''')

    # Table pour les gendarmes et leur NIGEND/spécialités
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS gendarmes (
        user_id INTEGER PRIMARY KEY,
        nigend TEXT NOT NULL UNIQUE,
        specialites TEXT
    )
    ''')

    # Table pour la configuration du bot
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    conn.commit()
    conn.close()

# --- Initialisation du Bot ---
intents = discord.Intents.default()
intents.members = True # Nécessaire pour accéder aux informations des membres
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Événement quand le bot est prêt ---
@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user}')
    init_db() # Crée la base de données et les tables si elles n'existent pas
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print(f"{len(synced)} commandes slash synchronisées.")
    except Exception as e:
        print(e)

# --- Commandes Slash ---

# Groupe de commandes pour le NIGEND
nigend_group = app_commands.Group(name="nigend", description="Gestion des NIGEND des gendarmes.")

@nigend_group.command(name="creer", description="Crée un NIGEND pour un membre.")
@app_commands.describe(membre="Le membre à qui attribuer le NIGEND.", nigend="Le numéro d'identification (ex: 123456).")
@app_commands.checks.has_permissions(administrator=True) # Seuls les admins peuvent faire ça
async def creer_nigend(interaction: discord.Interaction, membre: discord.Member, nigend: str):
    conn = sqlite3.connect('gendarmerie.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO gendarmes (user_id, nigend) VALUES (?, ?)", (membre.id, nigend))
        conn.commit()
        await interaction.response.send_message(f"Le NIGEND `{nigend}` a été créé et attribué à {membre.mention}.", ephemeral=True)
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"Erreur : Ce membre ou ce NIGEND existe déjà.", ephemeral=True)
    finally:
        conn.close()

@nigend_group.command(name="supprimer", description="Supprime le NIGEND d'un membre.")
@app_commands.describe(membre="Le membre dont le NIGEND doit être supprimé.")
@app_commands.checks.has_permissions(administrator=True)
async def supprimer_nigend(interaction: discord.Interaction, membre: discord.Member):
    conn = sqlite3.connect('gendarmerie.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gendarmes WHERE user_id = ?", (membre.id,))
    conn.commit()
    if cursor.rowcount > 0:
        await interaction.response.send_message(f"Le NIGEND de {membre.mention} a été supprimé.", ephemeral=True)
    else:
        await interaction.response.send_message(f"{membre.mention} n'a pas de NIGEND enregistré.", ephemeral=True)
    conn.close()

# Ajoute le groupe de commandes au bot
bot.tree.add_command(nigend_group, guild=discord.Object(id=GUILD_ID))


# Groupe de commandes pour le casier judiciaire
casier_group = app_commands.Group(name="casier", description="Gestion des casiers judiciaires.")

@casier_group.command(name="creer", description="Crée une nouvelle fiche de casier judiciaire.")
@app_commands.describe(
    prenom="Prénom de la personne.",
    nom="Nom de la personne.",
    date_faits="Date des faits (JJ/MM/AAAA).",
    infractions="Infractions commises (séparées par des virgules).",
    statut_judiciaire="Statut du dossier (ex: Enquête, Jugé, Classé sans suite).",
    age="Âge de la personne.",
    date_naissance="Date de naissance (JJ/MM/AAAA).",
    telephone="Numéro de téléphone.",
    profession="Profession de la personne."
)
async def creer_casier(interaction: discord.Interaction, prenom: str, nom: str, date_faits: str, infractions: str, statut_judiciaire: str, age: int = None, date_naissance: str = None, telephone: str = None, profession: str = None):
    # --- Vérification du rôle Gendarme ---
    conn_check = get_db_connection()
    gendarme_role_id_row = conn_check.execute("SELECT value FROM config WHERE key = 'gendarme_role_id'").fetchone()
    conn_check.close()

    if gendarme_role_id_row and gendarme_role_id_row['value']:
        gendarme_role = interaction.guild.get_role(int(gendarme_role_id_row['value']))
        if gendarme_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return
    else:
        # Si le rôle n'est pas configuré, on envoie un avertissement (ou on bloque)
        await interaction.response.send_message("⚠️ Le rôle Gendarme n'est pas configuré. Veuillez contacter un administrateur.", ephemeral=True)
        return

    conn = sqlite3.connect('gendarmerie.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO casiers (prenom, nom, age, date_naissance, telephone, profession, date_faits, infractions, statut_judiciaire) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (prenom, nom, age, date_naissance, telephone, profession, date_faits, infractions, statut_judiciaire)
    )
    conn.commit()
    casier_id = cursor.lastrowid
    conn.close()

    embed = discord.Embed(title="✅ Nouveau Casier Judiciaire Créé", color=discord.Color.green())
    embed.add_field(name="ID du Casier", value=casier_id, inline=False)
    embed.add_field(name="Identité", value=f"{prenom} {nom}", inline=False)
    embed.add_field(name="Date des faits", value=date_faits, inline=True)
    embed.add_field(name="Statut", value=statut_judiciaire, inline=True)
    embed.add_field(name="Infractions", value=infractions, inline=False)
    embed.set_footer(text=f"Casier créé par {interaction.user.display_name}")

    await interaction.response.send_message(embed=embed)

@casier_group.command(name="rechercher", description="Recherche un casier judiciaire par nom.")
@app_commands.describe(nom="Le nom de la personne à rechercher.")
async def rechercher_casier(interaction: discord.Interaction, nom: str):
    # --- Vérification du rôle Gendarme (identique à la création) ---
    conn_check = get_db_connection()
    gendarme_role_id_row = conn_check.execute("SELECT value FROM config WHERE key = 'gendarme_role_id'").fetchone()
    casier_log_channel_id_row = conn_check.execute("SELECT value FROM config WHERE key = 'casier_log_channel_id'").fetchone()
    conn_check.close()

    if gendarme_role_id_row and gendarme_role_id_row['value']:
        gendarme_role = interaction.guild.get_role(int(gendarme_role_id_row['value']))
        if gendarme_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True)
            return
    else:
        await interaction.response.send_message("⚠️ Le rôle Gendarme n'est pas configuré.", ephemeral=True)
        return

    # --- Recherche dans la base de données ---
    conn = get_db_connection()
    casiers = conn.execute("SELECT * FROM casiers WHERE nom LIKE ?", (f'%{nom}%',)).fetchall()
    conn.close()

    if not casiers:
        await interaction.response.send_message(f"Aucun casier trouvé pour le nom `{nom}`.", ephemeral=True)
        return

    # --- Envoi des résultats dans le salon configuré ---
    if casier_log_channel_id_row and casier_log_channel_id_row['value']:
        log_channel = bot.get_channel(int(casier_log_channel_id_row['value']))
        if log_channel:
            await interaction.response.send_message(f"✅ Les résultats de la recherche ont été envoyés dans {log_channel.mention}.", ephemeral=True)
            for casier in casiers:
                embed = discord.Embed(title=f"Résultat de recherche : {casier['prenom']} {casier['nom']}", color=discord.Color.blue())
                embed.add_field(name="ID Casier", value=casier['id'], inline=True)
                embed.add_field(name="Date des faits", value=casier['date_faits'], inline=True)
                embed.add_field(name="Statut", value=casier['statut_judiciaire'], inline=True)
                embed.add_field(name="Infractions", value=casier['infractions'], inline=False)
                await log_channel.send(embed=embed)
        else:
            await interaction.response.send_message("❌ Le salon de logs configuré est introuvable.", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ Le salon pour afficher les casiers n'est pas configuré.", ephemeral=True)

# Commande pour faire appel
@casier_group.command(name="appel", description="Faire une demande d'appel pour supprimer un casier.")
@app_commands.describe(id_casier="L'ID du casier pour lequel vous faites appel.")
async def appel_casier(interaction: discord.Interaction, id_casier: int):
    conn = sqlite3.connect('gendarmerie.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE casiers SET appel_status = 'En attente' WHERE id = ?", (id_casier,))
    conn.commit()
    
    if cursor.rowcount > 0:
        await interaction.response.send_message("Votre demande d'appel a été enregistrée. Elle sera examinée par un magistrat.", ephemeral=True)
        # Ici, on pourrait envoyer une notification dans un salon privé pour les magistrats/admins
        # log_channel = bot.get_channel(ID_DU_SALON_LOGS)
        # await log_channel.send(f"Nouvelle demande d'appel pour le casier n°{id_casier} par {interaction.user.mention}.")
    else:
        await interaction.response.send_message(f"Aucun casier trouvé avec l'ID {id_casier}.", ephemeral=True)
    
    conn.close()


bot.tree.add_command(casier_group, guild=discord.Object(id=GUILD_ID))

# --- Lancement du Bot et du Dashboard ---

def run_flask():
    # Lance le serveur Flask. `debug=False` est important quand on utilise le threading.
    app.run(host='0.0.0.0', port=30137, debug=False)

async def main():
    # Crée et démarre le thread pour le dashboard
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("Dashboard web démarré en arrière-plan sur le port 30137.")
    
    # Démarre le bot Discord
    await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Arrêt du bot et du serveur.")
