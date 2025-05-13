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

bot = commands.Bot(command_prefix='!', intents=intents)

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

        await channel.send("Parfait. Pour {0}, à partir de quel prix veux-tu être alerté ? (USD)".format(msg1.content.upper()))
        msg3 = await bot.wait_for('message', check=check, timeout=60)
        alerts[member.id] = {msg1.content.lower(): float(msg3.content)}
        save_data()

        await channel.send("Merci ! Tu es maintenant vérifié. Profite du serveur !")
        role = discord.utils.get(member.guild.roles, name="Vérifié")
        if role:
            await member.add_roles(role)
        user_verified.add(member.id)
        save_data()
        save_data()
    except asyncio.TimeoutError:
        await channel.send("Temps d'attente dépassé. Rejoins plus tard ou contacte un admin si tu as besoin d'aide.")

@bot.command()
async def alert(ctx, crypto: str, price: float):
    uid = ctx.author.id
    alerts.setdefault(uid, {})
    alerts[uid][crypto.lower()] = price
    save_data()
    await ctx.send(f"⚠️ Alerte active : {crypto.upper()} < {price}$")

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
        alerts.get(uid, {}).pop(crypto.lower(), None)
        save_data()
        await ctx.send(f"❌ Tu ne suis plus {crypto.upper()}")
    else:
        await ctx.send("Tu ne suis pas cette crypto.")

@bot.command()
async def disablealert(ctx, crypto: str):
    uid = ctx.author.id
    if uid in alerts and crypto.lower() in alerts[uid]:
        del alerts[uid][crypto.lower()]
        save_data()
        await ctx.send(f"🚫 Alerte sur {crypto.upper()} désactivée.")
    else:
        await ctx.send("Aucune alerte active sur cette crypto.")

# ========== TÂCHE ALERTES ============
@tasks.loop(seconds=60)
async def check_alerts():
    for uid, crypto_dict in alerts.items():
        user = await bot.fetch_user(uid)
        if not user:
            continue
        for crypto, threshold in crypto_dict.items():
            price = get_price(crypto)
            if price is not None and price <= threshold:
                await user.send(f"🚨 {crypto.upper()} est sous {threshold}$ (actuel : {price}$)")


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

`!alert1 <monnaie> <prix>` → Alerte simple par message (niveau 1)
`!alert2 <monnaie> <prix>` → Alerte avec mention (niveau 2)
`!alert3 <monnaie> <prix>` → Alerte vocale si activée (niveau 3)
`!disablealert <monnaie>` → Supprime les alertes sur cette crypto

`!news <monnaie>` → Donne le prix actuel de la crypto
`!graph <monnaie>` → Affiche un graphique de l’évolution sur 24h
""", inline=False)

    embed.add_field(name="🔎 Infos", value="""
`!ping` → Vérifie si le bot est actif
`!avatar` → Ton avatar
`!userinfo @membre` → Infos sur un membre
`!server` → Infos sur le serveur
`!say <texte>` → Répète ton texte
`!suggest <idée>` → Propose une idée
""", inline=False)

    if ctx.author.guild_permissions.administrator:
        embed.add_field(name="🔐 Admins", value="""
`!announce <msg>` → Annonce visible par tout le monde
`!dm @membre <msg>` → Envoie un DM
""", inline=False)

    await ctx.send(embed=embed)


# ========== DÉMARRAGE ============
keep_alive()
token = os.environ['TOKEN']
bot.run(token)
