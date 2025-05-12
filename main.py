import discord
import os
import asyncio
import requests
from discord.ext import commands, tasks
import matplotlib.pyplot as plt
import io
from keep_alive import keep_alive

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

alerts = {}  # user_id: {crypto: seuil}
tracked_cryptos = {}  # user_id: [cryptos]
user_channels = {}  # user_id: channel_id
user_verified = set()

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
        await channel.send(f"Ok, tu suis maintenant {msg1.content.upper()}\nUne deuxième crypto ? Tape 'non' si tu ne veux pas.")
        msg2 = await bot.wait_for('message', check=check, timeout=60)
        if msg2.content.lower() != 'non':
            tracked_cryptos[member.id].append(msg2.content.lower())

        await channel.send("Parfait. Pour {0}, à partir de quel prix veux-tu être alerté ? (USD)".format(msg1.content.upper()))
        msg3 = await bot.wait_for('message', check=check, timeout=60)
        alerts[member.id] = {msg1.content.lower(): float(msg3.content)}

        await channel.send("Merci ! Tu es maintenant vérifié. Profite du serveur !")
        role = discord.utils.get(member.guild.roles, name="Vérifié")
        if role:
            await member.add_roles(role)
        user_verified.add(member.id)
    except asyncio.TimeoutError:
        await channel.send("Temps d'attente dépassé. Rejoins plus tard ou contacte un admin si tu as besoin d'aide.")

# ========== COMMANDES ============
@bot.command()
async def track(ctx, crypto: str):
    uid = ctx.author.id
    tracked_cryptos.setdefault(uid, [])
    if len(tracked_cryptos[uid]) >= 2:
        await ctx.send("Tu ne peux suivre que 2 cryptos maximum (version gratuite).")
        return
    if crypto.lower() not in tracked_cryptos[uid]:
        tracked_cryptos[uid].append(crypto.lower())
        await ctx.send(f"✅ Tu suis maintenant {crypto.upper()}")
    else:
        await ctx.send("Tu suis déjà cette crypto.")

@bot.command()
async def untrack(ctx, crypto: str):
    uid = ctx.author.id
    if uid in tracked_cryptos and crypto.lower() in tracked_cryptos[uid]:
        tracked_cryptos[uid].remove(crypto.lower())
        alerts.get(uid, {}).pop(crypto.lower(), None)
        await ctx.send(f"❌ Tu ne suis plus {crypto.upper()}")
    else:
        await ctx.send("Tu ne suis pas cette crypto.")

@bot.command()
async def mycryptos(ctx):
    uid = ctx.author.id
    cryptos = tracked_cryptos.get(uid, [])
    await ctx.send(f"🔎 Cryptos suivies : {', '.join(cryptos) if cryptos else 'Aucune'}")

@bot.command()
async def alert(ctx, crypto: str, price: float):
    uid = ctx.author.id
    alerts.setdefault(uid, {})
    alerts[uid][crypto.lower()] = price
    await ctx.send(f"⚠️ Alerte active : {crypto.upper()} < {price}$")

@bot.command()
async def disablealert(ctx, crypto: str):
    uid = ctx.author.id
    if uid in alerts and crypto.lower() in alerts[uid]:
        del alerts[uid][crypto.lower()]
        await ctx.send(f"🚫 Alerte sur {crypto.upper()} désactivée.")
    else:
        await ctx.send("Aucune alerte active sur cette crypto.")

@bot.command()
async def news(ctx, crypto: str):
    price = get_price(crypto.lower())
    if price is None:
        await ctx.send("❌ Crypto inconnue ou erreur d'API.")
        return
    await ctx.send(f"📰 Actu de {crypto.upper()}\nPrix actuel : ${price:.2f} USD\n(D'autres actus bientôt disponibles.)")

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
async def ping(ctx):
    await ctx.send("🏓 Je suis actif !")

@bot.command()
async def info(ctx):
    embed = discord.Embed(title="TrackBot", description="Bot d'alerte crypto personnalisé.", color=0x00ffcc)
    embed.add_field(name="Auteur", value="Toi 🙌", inline=True)
    embed.add_field(name="Commandes", value="Tape !help pour tout voir", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def say(ctx, *, text):
    await ctx.send(text)

@bot.command()
async def avatar(ctx):
    await ctx.send(ctx.author.avatar.url if ctx.author.avatar else "Aucun avatar")

@bot.command()
async def server(ctx):
    await ctx.send(f"📌 Serveur : {ctx.guild.name} | Membres : {ctx.guild.member_count}")

@bot.command()
async def userinfo(ctx, user: discord.User):
    embed = discord.Embed(title="Infos utilisateur", color=0x00ffaa)
    embed.set_thumbnail(url=user.avatar.url if user.avatar else "")
    embed.add_field(name="Nom", value=user.name)
    embed.add_field(name="ID", value=user.id)
    await ctx.send(embed=embed)

@bot.command()
async def suggest(ctx, *, message):
    await ctx.send(f"💡 Suggestion reçue : `{message}`. Merci {ctx.author.mention} !")

@bot.command()
@commands.has_permissions(administrator=True)
async def announce(ctx, *, msg):
    for channel in ctx.guild.text_channels:
        await channel.send(f"📢 Annonce : {msg}")

@bot.command()
@commands.has_permissions(administrator=True)
async def dm(ctx, member: discord.Member, *, message):
    try:
        await member.send(f"📬 Message d'admin : {message}")
        await ctx.send("Message envoyé.")
    except:
        await ctx.send("Impossible d'envoyer le message.")

# ========== TÂCHE ALERTES ============
@tasks.loop(seconds=60)
def check_alerts():
    for uid, crypto_dict in alerts.items():
        user = bot.get_user(uid)
        if not user:
            continue
        for crypto, threshold in crypto_dict.items():
            price = get_price(crypto)
            if price is not None and price <= threshold:
                asyncio.create_task(user.send(f"🚨 {crypto.upper()} est sous {threshold}$ (actuel : {price}$)"))

# ========== DÉMARRAGE ============
keep_alive()
token = os.environ['TOKEN']
bot.run(token)
