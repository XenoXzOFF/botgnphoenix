import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from datetime import datetime

# --- Configuration ---
# Remplace par ton vrai token dans un fichier de configuration ou une variable d'environnement
# Ne jamais écrire le token directement dans le code !
BOT_TOKEN = "TON_TOKEN_DISCORD_ICI" 
GUILD_ID = 123456789012345678 # ID de ton serveur Discord (clic droit sur le serveur > Copier l'ID)

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
    # On pourrait ajouter une vérification de rôle ici pour s'assurer que seuls les gendarmes peuvent le faire
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

# --- Lancement du bot ---
bot.run(BOT_TOKEN)
