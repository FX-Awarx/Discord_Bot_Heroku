import discord
import os
import asyncio
import requests
from discord.ext import commands, tasks
import matplotlib.pyplot as plt
import io
import json
from keep_alive import keep_alive

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)


DATA_FILE = 'data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            return {
                'alerts': {int(k): v for k, v in data.get('alerts', {}).items()},
                'tracked_cryptos': {int(k): v for k, v in data.get('tracked_cryptos', {}).items()},
                'user_verified': set(map(int, data.get('user_verified', [])))
            }
    return {'alerts': {}, 'tracked_cryptos': {}, 'user_verified': set()}

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump({
            'alerts': alerts,
            'tracked_cryptos': tracked_cryptos,
            'user_verified': list(user_verified)
        }, f)

data = load_data()
alerts = data['alerts']
tracked_cryptos = data['tracked_cryptos']
user_verified = data['user_verified']
user_channels = {}

# ======== API COINGECKO ========
def get_price(symbol='bitcoin'):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd"
    try:
        response = requests.get(url)
        if response.status_code != 200:
            return None
        data = response.json()
        return data.get(symbol, {}).get('usd')
    except:
        return None

def get_price_history(symbol='bitcoin'):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart?vs_currency=usd&days=1"
    try:
        response = requests.get(url)
        if response.status_code != 200:
            return []
        data = response.json()
        return [point[1] for point in data.get("prices", [])]
    except:
        return []

# ========== EVENTS ============
@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user}")
    check_alerts.start()

@bot.event
async def on_member_join(member):
    guild = member.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    channel = await guild.create_text_channel(f"param-{member.name}", overwrites=overwrites)
    user_channels[member.id] = channel.id
    await start_interaction(member, channel)

async def start_interaction(member, channel):
    def check(m):
        return m.channel == channel and m.author == member

    await channel.send("Bienvenue ✅\nTu veux suivre l'actualité crypto ? On va personnaliser tout ça.\nDonne-moi ta première crypto (ex: bitcoin):")
    try:
        msg1 = await bot.wait_for('message', check=check, timeout=120)
        tracked_cryptos[member.id] = [msg1.content.lower()]
        save_data()
        await channel.send(f"Ok, tu suis maintenant {msg1.content.upper()}\nUne deuxième crypto ? Tape 'non' si tu ne veux pas.")
        msg2 = await bot.wait_for('message', check=check, timeout=60)
        if msg2.content.lower() != 'non':
            tracked_cryptos[member.id].append(msg2.content.lower())
            save_data()

        await channel.send(f"Parfait. Pour {msg1.content.upper()}, à partir de quel prix veux-tu être alerté ? (USD)")
        msg3 = await bot.wait_for('message', check=check, timeout=60)
        alerts.setdefault(member.id, {})
        alerts[member.id][msg1.content.lower()] = {"1": float(msg3.content)}
        save_data()

        await channel.send("Merci ! Tu es maintenant vérifié. Profite du serveur !")
        role = discord.utils.get(member.guild.roles, name="Vérifié")
        if role:
            await member.add_roles(role)
        user_verified.add(member.id)
        save_data()
    except asyncio.TimeoutError:
        await channel.send("Temps d'attente dépassé. Rejoins plus tard ou contacte un admin si tu as besoin d'aide.")

@bot.command()
async def alert1(ctx, crypto: str, price: float):
    uid = ctx.author.id
    crypto = crypto.lower()
    alerts.setdefault(uid, {})
    alerts[uid].setdefault(crypto, {})
    alerts[uid][crypto]["1"] = price
    save_data()

    await ctx.send(f"✅ Alerte NIVEAU 1 enregistrée pour {crypto.upper()} si le prix descend sous {price}$.")

    current = get_price(crypto)
    if current is None:
        await ctx.send("⚠️ Impossible de vérifier le prix actuel.")
    elif current <= price:
        await ctx.author.send(f"🚨 Alerte immédiate (niveau 1) : {crypto.upper()} est à {current}$ (seuil : {price}$)")
    else:
        await ctx.send(f"ℹ️ Prix actuel de {crypto.upper()} : {current}$ — aucun signal.")

@bot.command()
async def disablealert1(ctx, crypto: str):
    uid = ctx.author.id
    crypto = crypto.lower()
    if uid in alerts and crypto in alerts[uid] and "1" in alerts[uid][crypto]:
        del alerts[uid][crypto]["1"]
        save_data()
        await ctx.send(f"🛑 Alerte niveau 1 désactivée pour {crypto.upper()}.")
    else:
        await ctx.send("Aucune alerte niveau 1 active sur cette crypto.")

@bot.command()
async def alert2(ctx, crypto: str, price: float):
    uid = ctx.author.id
    crypto = crypto.lower()
    alerts.setdefault(uid, {})
    alerts[uid].setdefault(crypto, {})
    alerts[uid][crypto]["2"] = price
    save_data()

    await ctx.send(f"✅ Alerte NIVEAU 2 enregistrée pour {crypto.upper()} si le prix descend sous {price}$.")

    current = get_price(crypto)
    if current is None:
        await ctx.send("⚠️ Impossible de vérifier le prix actuel.")
    elif current <= price:
        await ctx.send(f"🚨 {ctx.author.mention} Alerte immédiate (niveau 2) : {crypto.upper()} est à {current}$")
    else:
        await ctx.send(f"ℹ️ Prix actuel de {crypto.upper()} : {current}$ — aucun signal.")

@bot.command()
async def disablealert2(ctx, crypto: str):
    uid = ctx.author.id
    crypto = crypto.lower()
    if uid in alerts and crypto in alerts[uid] and "2" in alerts[uid][crypto]:
        del alerts[uid][crypto]["2"]
        save_data()
        await ctx.send(f"🔕 Alerte niveau 2 désactivée pour {crypto.upper()}.")
    else:
        await ctx.send("Aucune alerte niveau 2 active sur cette crypto.")

@bot.command()
async def alert3(ctx, crypto: str, price: float):
    uid = ctx.author.id
    crypto = crypto.lower()
    alerts.setdefault(uid, {})
    alerts[uid].setdefault(crypto, {})
    alerts[uid][crypto]["3"] = price
    save_data()

    await ctx.send(f"✅ Alerte NIVEAU 3 enregistrée pour {crypto.upper()} si le prix descend sous {price}$.")

    current = get_price(crypto)
    if current is None:
        await ctx.send("⚠️ Impossible de vérifier le prix actuel.")
    elif current <= price:
        await play_alert_audio(ctx)
    else:
        await ctx.send(f"ℹ️ Prix actuel de {crypto.upper()} : {current}$ — aucun signal.")

@bot.command()
async def disablealert3(ctx, crypto: str):
    uid = ctx.author.id
    crypto = crypto.lower()
    if uid in alerts and crypto in alerts[uid] and "3" in alerts[uid][crypto]:
        del alerts[uid][crypto]["3"]
        save_data()
        await ctx.send(f"📴 Alerte niveau 3 désactivée pour {crypto.upper()}.")
    else:
        await ctx.send("Aucune alerte niveau 3 active sur cette crypto.")


@bot.command()
async def track(ctx, crypto: str):
    uid = ctx.author.id
    tracked_cryptos.setdefault(uid, [])
    if len(tracked_cryptos[uid]) >= 2:
        await ctx.send("Tu ne peux suivre que 2 cryptos maximum (version gratuite).")
        return
    if crypto.lower() not in tracked_cryptos[uid]:
        tracked_cryptos[uid].append(crypto.lower())
        save_data()
        await ctx.send(f"✅ Tu suis maintenant {crypto.upper()}")
    else:
        await ctx.send("Tu suis déjà cette crypto.")

@bot.command()
async def untrack(ctx, crypto: str):
    uid = ctx.author.id
    if uid in tracked_cryptos and crypto.lower() in tracked_cryptos[uid]:
        tracked_cryptos[uid].remove(crypto.lower())
        s.get(uid, {}).pop(crypto.lower(), None)
        save_data()
        await ctx.send(f"❌ Tu ne suis plus {crypto.upper()}")
    else:
        await ctx.send("Tu ne suis pas cette crypto.")

# ========== TÂCHE ALERTES ============
@tasks.loop(minutes=5)
async def check_alerts():
    if not hasattr(check_alerts, "last_sent"):
        check_alerts.last_sent = {}

    for uid, crypto_dict in alerts.items():
        user = await bot.fetch_user(uid)
        if not user:
            continue

        for crypto, config in crypto_dict.items():
            level = config.get("level")
            threshold = config.get("threshold")
            price = get_price(crypto)

            if price is not None and price <= threshold:
                key = f"{uid}_{crypto}"
                now = asyncio.get_event_loop().time()
                last_time = check_alerts.last_sent.get(key, 0)

                if now - last_time >= 3600:  # relancer seulement 1 fois/h
                    if level == 1:
                        await user.send(f"🔔 Alerte NIVEAU 1 : {crypto.upper()} est sous {threshold}$ → {price}$")
                    elif level == 2:
                        await user.send(f"🚨 Alerte NIVEAU 2 : {crypto.upper()} est sous {threshold}$ → {price}$")
                    elif level == 3:
                        await user.send(f"📞 Alerte NIVEAU 3 (appel simulé) : {crypto.upper()} à {price}$")

                    check_alerts.last_sent[key] = now


@bot.command()
async def mycryptos(ctx):
    uid = ctx.author.id
    cryptos = tracked_cryptos.get(uid, [])
    await ctx.send(f"🔎 Cryptos suivies : {', '.join(cryptos) if cryptos else 'Aucune'}")

@bot.command()
async def news(ctx, crypto: str):
    price = get_price(crypto.lower())
    if price is None:
        await ctx.send("❌ Crypto inconnue ou erreur d'API.")
        return

    embed = discord.Embed(
        title=f"📰 Infos sur {crypto.upper()}",
        description=f"Voici les dernières données disponibles.",
        color=0x3498db
    )
    embed.add_field(name="💰 Prix actuel", value=f"{price:.2f} USD", inline=False)
    embed.set_footer(text="D'autres actualités seront disponibles prochainement.")
    await ctx.send(embed=embed)



@bot.command()
async def graph(ctx, crypto: str):
    data = get_price_history(crypto.lower())
    if not data:
        await ctx.send("❌ Données indisponibles pour cette crypto ou API inaccessible.")
        return
    plt.figure()
    plt.plot(data, color='blue')
    plt.title(f"Évolution de {crypto.upper()} (24h)")
    plt.xlabel("Temps")
    plt.ylabel("Prix (USD)")
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    file = discord.File(fp=buf, filename='graph.png')
    await ctx.send(file=file)
    buf.close()

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="📚 Aide TrackBot",
        description="Voici toutes les commandes disponibles avec leur usage :",
        color=0x1abc9c
    )

    embed.add_field(name="🎯 Commandes Utilisateur", value="""
`!track <monnaie>` → Commence à suivre une crypto (ex: btc, eth)
`!untrack <monnaie>` → Arrête de suivre une crypto
`!mycryptos` → Liste les cryptos que tu suis

`!alert1 <monnaie> <prix>` → Alerte par message (niveau 1)
`!alert2 <monnaie> <prix>` → Alerte avec mention (niveau 2)
`!alert3 <monnaie> <prix>` → Alerte vocale (niveau 3, si activée)

`!disablealert1 <monnaie>` → Supprime uniquement l'alerte niveau 1
`!disablealert2 <monnaie>` → Supprime uniquement l'alerte niveau 2
`!disablealert3 <monnaie>` → Supprime uniquement l'alerte niveau 3

`!news <monnaie>` → Donne le prix actuel
`!graph <monnaie>` → Affiche un graphique 24h
""", inline=False)

    embed.add_field(name="🔎 Infos", value="""
`!ping` → Vérifie si le bot est actif
`!avatar` → Ton avatar
`!userinfo @membre` → Infos sur un membre
`!server` → Infos sur le serveur
`!say <texte>` → Le bot répète ton message
`!suggest <idée>` → Propose une idée
""", inline=False)

    if ctx.author.guild_permissions.administrator:
        embed.add_field(name="🔐 Admins", value="""
`!announce <message>` → Annonce globale dans tous les salons
`!dm @membre <message>` → Envoie un DM personnalisé
""", inline=False)

    await ctx.send(embed=embed)


@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong ! Je suis actif.")

@bot.command()
async def avatar(ctx):
    avatar_url = ctx.author.avatar.url if ctx.author.avatar else None
    if avatar_url:
        await ctx.send(avatar_url)
    else:
        await ctx.send("Tu n'as pas d'avatar Discord.")

@bot.command()
async def server(ctx):
    await ctx.send(f"📌 Serveur : **{ctx.guild.name}** | 👥 Membres : {ctx.guild.member_count}")

@bot.command()
async def say(ctx, *, text: str):
    await ctx.send(text)

@bot.command()
async def info(ctx):
    embed = discord.Embed(title="TrackBot", description="Bot d'alerte crypto personnalisé.", color=0x00ffcc)
    embed.add_field(name="👨‍💻 Auteur", value="Toi 🙌", inline=True)
    embed.add_field(name="📋 Commandes", value="Tape `!help` pour tout voir", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def userinfo(ctx, user: discord.User):
    embed = discord.Embed(title="Infos utilisateur", color=0x00ffaa)
    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    embed.add_field(name="Nom", value=user.name)
    embed.add_field(name="ID", value=user.id)
    embed.add_field(name="Compte créé le", value=user.created_at.strftime('%d %B %Y'))
    await ctx.send(embed=embed)

@bot.command()
async def suggest(ctx, *, idea: str):
    channel = discord.utils.get(ctx.guild.text_channels, name="suggest")
    if channel is None:
        await ctx.send("❌ Aucun salon nommé 'suggest' trouvé.")
        return
    embed = discord.Embed(title="💡 Nouvelle suggestion", description=idea, color=0xf1c40f)
    embed.set_footer(text=f"Proposé par {ctx.author} • {ctx.message.created_at.strftime('%d/%m/%Y %H:%M')}")
    await channel.send(embed=embed)
    await ctx.send("✅ Suggestion envoyée dans #suggest")

@bot.command()
@commands.has_permissions(administrator=True)
async def dm(ctx, member: discord.Member, *, message):
    try:
        await member.send(f"📬 Message de l'admin : {message}")
        await ctx.send("✉️ Message envoyé avec succès.")
    except:
        await ctx.send("❌ Impossible d'envoyer le message.")

@bot.command()
@commands.has_permissions(administrator=True)
async def announce(ctx, *, msg):
    for channel in ctx.guild.text_channels:
        try:
            await channel.send(f"📢 Annonce : {msg}")
        except:
            continue

async def play_alert_audio(ctx):
    voice_channel = discord.utils.get(ctx.guild.voice_channels, name="alert")  # nom exact du salon vocal
    if voice_channel is None:
        await ctx.send("❌ Aucun salon vocal nommé 'alert' trouvé.")
        return

    if ctx.voice_client:
        await ctx.voice_client.disconnect()

    vc = await voice_channel.connect()

    if not os.path.isfile("alert.mp3"):
        await ctx.send("❌ Fichier audio 'alert.mp3' non trouvé.")
        await vc.disconnect()
        return

    vc.play(discord.FFmpegPCMAudio("alert.mp3"))
    while vc.is_playing():
        await asyncio.sleep(1)

    await vc.disconnect()



# ========== DÉMARRAGE ============
keep_alive()
token = os.environ['TOKEN']
bot.run(token)
