import discord
from discord.ext import commands
import random
import psycopg2
import os
from asyncio import sleep
from datetime import datetime
from config import DISCORD_TOKEN

# ==========================================
# KONFIGURASI DATABASE POSTGRESQL (pgAdmin 4 / Cloud)
# ==========================================
# Ganti string di bawah dengan URL koneksi pgAdmin/PostgreSQL Anda untuk testing lokal,
# atau biarkan menggunakan os.getenv untuk deployment cloud (Render/Railway).
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:passwordanda@localhost:5432/nama_database")

conn = psycopg2.connect(DATABASE_URL, sslmode='require' if 'render' in DATABASE_URL.lower() or 'railway' in DATABASE_URL.lower() else 'prefer')
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS players (
        user_id BIGINT PRIMARY KEY,
        name TEXT,
        level INTEGER,
        hp INTEGER,
        max_hp INTEGER,
        attack INTEGER,
        gold INTEGER,
        bank_gold INTEGER DEFAULT 0,
        xp INTEGER,
        last_quest TEXT,
        hunger INTEGER DEFAULT 100,
        pet_name TEXT DEFAULT 'Tidak Ada',
        pet_hunger INTEGER DEFAULT 100,
        pet_attack INTEGER DEFAULT 0,
        location TEXT DEFAULT 'Hutan Pemula'
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS inventory (
        user_id BIGINT,
        item_name TEXT,
        item_type TEXT,
        quantity INTEGER,
        enhance_level INTEGER DEFAULT 0,
        durability INTEGER DEFAULT 100,
        PRIMARY KEY (user_id, item_name)
    )
''')
conn.commit()

# ==========================================
# FUNGSI PENGHITUNG XP BERTAHAP (PROGRESIF)
# ==========================================
def get_xp_req(level):
    reqs = {1: 100, 2: 150, 3: 200, 4: 250, 5: 350}
    if level in reqs:
        return reqs[level]
    
    req = 350
    for _ in range(6, level + 1):
        req = int(req * 1.05)
    return req

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Set untuk melacak pemain yang sedang dalam pertempuran aktif
active_combats = set()

OWNER_ID = 752400201196503070  # ID Discord Anda

def check_is_owner_ctx(ctx):
    return ctx.author.id == OWNER_ID

@bot.event
async def on_ready():
    print(f"Bot {bot.user.name} Ultimate Epic RPG (PostgreSQL Edition) sudah aktif!")

# Middleware global untuk mencegah pemain mengetik perintah saat sedang bertarung
@bot.check
async def globally_block_during_combat(ctx):
    if ctx.author.id in active_combats:
        await ctx.send(f"⚠️ {ctx.author.mention}, kamu sedang berada di tengah pertarungan! Selesaikan atau kabur terlebih dahulu.", delete_after=5)
        return False
    return True

@bot.command(name="start")
async def start_game(ctx):
    user_id = ctx.author.id
    cursor.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
    if cursor.fetchone():
        await ctx.send(f"{ctx.author.mention}, kamu sudah terdaftar di dunia Hardcore RPG!")
    else:
        cursor.execute("INSERT INTO players (user_id, name, level, hp, max_hp, attack, gold, xp, last_quest, location) VALUES (%s, %s, 1, 80, 80, 10, 30, 0, '', 'Hutan Pemula')", 
                       (user_id, ctx.author.name))
        cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, 'Health Potion', 'potion', 3, 0, 100) ON CONFLICT (user_id, item_name) DO NOTHING", (user_id,))
        cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, 'Roti Bakar', 'food', 3, 0, 100) ON CONFLICT (user_id, item_name) DO NOTHING", (user_id,))
        cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, 'Kayu Tumpul', 'weapon', 1, 0, 100) ON CONFLICT (user_id, item_name) DO NOTHING", (user_id,))
        cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, 'Baju Kain', 'armor', 1, 0, 100) ON CONFLICT (user_id, item_name) DO NOTHING", (user_id,))
        conn.commit()
        await ctx.send(f"⚠️ Selamat datang di **Ultimate PvE RPG**, {ctx.author.mention}! Gunakan `!bag` untuk membuka tas interaktifmu.")

@bot.command(name="profile")
async def profile(ctx):
    user_id = ctx.author.id
    cursor.execute("SELECT name, level, hp, max_hp, attack, gold, bank_gold, xp, hunger, pet_name, pet_hunger, pet_attack, location FROM players WHERE user_id = %s", (user_id,))
    player = cursor.fetchone()
    
    if not player:
        return await ctx.send("Belum punya karakter! Ketik `!start`.")
    
    name, level, hp, max_hp, attack, gold, bank_gold, xp, hunger, pet_name, pet_hunger, pet_attack, location = player
    
    cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Health Potion'", (user_id,))
    p_data = cursor.fetchone()
    potions = p_data[0] if p_data else 0

    cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Roti Bakar'", (user_id,))
    f_data = cursor.fetchone()
    foods = f_data[0] if f_data else 0

    cursor.execute("SELECT item_name, enhance_level, durability FROM inventory WHERE user_id = %s AND item_type IN ('weapon', 'armor')", (user_id,))
    gear_list = [f"{g[0]} (+{g[1]}) [Dur: {g[2]}%]" for g in cursor.fetchall()]
    gear_str = ", ".join(gear_list) if gear_list else "Tidak ada"

    max_xp_needed = get_xp_req(level)

    embed = discord.Embed(title=f"💀 PvE Profile: {name}", color=discord.Color.dark_red())
    user_avatar = ctx.author.display_avatar.url
    embed.set_thumbnail(url=user_avatar)

    embed.add_field(name="Level / XP", value=f"Lv. {level} ({xp}/{max_xp_needed})", inline=True)
    embed.add_field(name="HP", value=f"{hp}/{max_hp}", inline=True)
    embed.add_field(name="Attack", value=attack, inline=True)
    embed.add_field(name="Lokasi Saat Ini", value=f"🗺️ {location}", inline=True)
    embed.add_field(name="Gold Dompet / Bank", value=f"🪙 {gold} | 🏦 {bank_gold}", inline=True)
    embed.add_field(name="Kelaparan", value=f"🍖 {hunger}%", inline=True)
    embed.add_field(name="Logistik", value=f"🧪 Potion: {potions} | 🍞 Roti: {foods}", inline=False)
    embed.add_field(name="Perlengkapan", value=f"🛡️ {gear_str}", inline=False)
    embed.add_field(name="Pet Kompanen", value=f"🐾 {pet_name} | Lapar: {pet_hunger}% | Atk: +{pet_attack}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="eat")
async def eat(ctx):
    user_id = ctx.author.id
    cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Roti Bakar'", (user_id,))
    bread = cursor.fetchone()
    
    if not bread or bread[0] <= 0:
        return await ctx.send("❌ Roti Bakar kamu habis! Beli di `!shop`.")
        
    cursor.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = %s AND item_name = 'Roti Bakar'", (user_id,))
    cursor.execute("UPDATE players SET hunger = 100 WHERE user_id = %s", (user_id,))
    conn.commit()
    await ctx.send(f"🍞 {ctx.author.mention} memakan Roti Bakar. Tingkat kelaparan kembali pulih menjadi **100%**!")

# ----------------------------------------------------
# 1. SISTEM INVENTARIS INTERAKTIF DENGAN TOMBOL
# ----------------------------------------------------
class InventoryView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

    @discord.ui.button(label="Minum Potion 🧪", style=discord.ButtonStyle.green)
    async def drink_potion(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Ini bukan tas milikmu!", ephemeral=True)
        
        cursor.execute("SELECT hp, max_hp FROM players WHERE user_id = %s", (self.user_id,))
        p = cursor.fetchone()
        if p[0] >= p[1]: return await interaction.response.send_message("HP sudah penuh!", ephemeral=True)
        
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Health Potion'", (self.user_id,))
        pot = cursor.fetchone()
        if not pot or pot[0] <= 0: return await interaction.response.send_message("Health Potion habis!", ephemeral=True)
        
        cursor.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = %s AND item_name = 'Health Potion'", (self.user_id,))
        cursor.execute("UPDATE players SET hp = %s WHERE user_id = %s", (p[1], self.user_id))
        conn.commit()
        await interaction.response.send_message(f"🧪 Berhasil meminum Potion! HP pulih penuh menjadi {p[1]}.", ephemeral=True)

    @discord.ui.button(label="Makan Roti 🍞", style=discord.ButtonStyle.blurple)
    async def eat_bread(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Ini bukan tas milikmu!", ephemeral=True)
            
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Roti Bakar'", (self.user_id,))
        bread = cursor.fetchone()
        if not bread or bread[0] <= 0: return await interaction.response.send_message("Roti Bakar habis!", ephemeral=True)
        
        cursor.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = %s AND item_name = 'Roti Bakar'", (self.user_id,))
        cursor.execute("UPDATE players SET hunger = 100 WHERE user_id = %s", (self.user_id,))
        conn.commit()
        await interaction.response.send_message("🍞 Memakan Roti Bakar. Kelaparan pulih menjadi 100%.", ephemeral=True)

@bot.command(name="bag", aliases=["inventory"])
async def bag(ctx):
    user_id = ctx.author.id
    cursor.execute("SELECT item_name, item_type, quantity, enhance_level, durability FROM inventory WHERE user_id = %s", (user_id,))
    items = cursor.fetchall()
    
    if not items: return await ctx.send("Tas kamu kosong!")
    
    embed = discord.Embed(title=f"🎒 Tas Penyimpanan: {ctx.author.name}", color=discord.Color.dark_green())
    embed.set_thumbnail(url="https://media.discordapp.net/attachments/1561653719970484304/1561659070719721532/backpack_1.png?ex=6ad727d8&is=6ad5d658&hm=b1eded664a3581216481ed35cdc6cccc4ed62fae5ea398a60af324abb37b7063&=&format=webp&quality=lossless")

    for item in items:
        name, item_type, qty, enh, dur = item
        if item_type in ('weapon', 'armor'):
            embed.add_field(name=f"• {name}", value=f"Jumlah: {qty} | Enhance: +{enh} | Dur: {dur}%", inline=False)
        else:
            embed.add_field(name=f"• {name}", value=f"Jumlah: {qty}", inline=False)
        
    view = InventoryView(user_id)
    await ctx.send(embed=embed, view=view)

# ----------------------------------------------------
# 2. KELAS TOMBOL INTERAKSI LANJUT SETELAH MENANG
# ----------------------------------------------------
class ContinueHuntView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=30)
        self.ctx = ctx

    @discord.ui.button(label="🌲 Lanjut Berburu", style=discord.ButtonStyle.green)
    async def continue_hunt(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Ini bukan petualanganmu!", ephemeral=True)
            
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)
        await trigger_hunt(self.ctx)

    @discord.ui.button(label="🏛️ Kembali ke Kota", style=discord.ButtonStyle.gray)
    async def back_to_town(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Ini bukan petualanganmu!", ephemeral=True)
            
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(content="🏛️ Kamu kembali ke gerbang kota dengan selamat.", view=self)

# ----------------------------------------------------
# 3. KELAS INTERACTIVE COMBAT VIEW (DENGAN TIMEOUT 45 DETIK)
# ----------------------------------------------------
class CombatView(discord.ui.View):
    def __init__(self, ctx, player, monster):
        super().__init__(timeout=45)
        self.ctx = ctx
        self.player = player 
        self.monster = monster 
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.player[0]:
            return True
        await interaction.response.send_message("Ini bukan pertarunganmu!", ephemeral=True)
        return False

    async def on_timeout(self):
        user_id = self.player[0]
        active_combats.discard(user_id)
        
        for child in self.children:
            child.disabled = True
            
        if self.message:
            try:
                embed = self.message.embeds[0]
                embed.color = discord.Color.dark_gray()
                embed.description = "⌛ **Pertarungan Kedaluwarsa!** Kamu terlalu lama tidak merespons, monster kabur ke dalam kegelapan. Blokir pertarungan dibuka kembali."
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

    @discord.ui.button(label="⚔️ Serang", style=discord.ButtonStyle.red)
    async def attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_turn(interaction, action="attack")

    @discord.ui.button(label="🛡️ Bertahan", style=discord.ButtonStyle.blurple)
    async def defend_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_turn(interaction, action="defend")

    @discord.ui.button(label="🧪 Minum Potion", style=discord.ButtonStyle.green)
    async def potion_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_turn(interaction, action="potion")

    @discord.ui.button(label="🏃 Kabur", style=discord.ButtonStyle.gray)
    async def run_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_turn(interaction, action="run")

    async def process_turn(self, interaction: discord.Interaction, action: str):
        user_id = self.player[0]
        name, level, hp, max_hp, attack, gold, xp, hunger, pet_hunger, pet_attack, location = self.player[1:]
        
        effective_attack = attack if hunger > 20 else int(attack * 0.5)
        if pet_hunger > 10: effective_attack += pet_attack

        m_name = self.monster["name"]
        m_hp = self.monster["hp"]
        m_atk = self.monster["attack"]

        log_text = ""

        if action == "run":
            if random.random() < 0.60: 
                for child in self.children: child.disabled = True
                active_combats.discard(user_id)
                await interaction.response.edit_message(content=f"🏃 Kamu berhasil melarikan diri dari **{m_name}** dengan selamat!", view=self)
                self.stop()
                return
            else:
                log_text += f"❌ Gagal kabur! **{m_name}** mencegat jalur pelarianmu.\n"

        elif action == "potion":
            cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Health Potion'", (user_id,))
            pot = cursor.fetchone()
            if not pot or pot[0] <= 0:
                await interaction.response.send_message("❌ Health Potion kamu habis!", ephemeral=True)
                return
            if hp >= max_hp:
                await interaction.response.send_message("❌ HP kamu sudah penuh!", ephemeral=True)
                return
            
            cursor.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = %s AND item_name = 'Health Potion'", (user_id,))
            hp = max_hp
            cursor.execute("UPDATE players SET hp = %s WHERE user_id = %s", (hp, user_id))
            conn.commit()
            
            log_text += f"🧪 Kamu meminum Health Potion di tengah pertempuran! HP pulih penuh menjadi **{hp}/{max_hp}**.\n"

        elif action == "attack":
            p_dmg = random.randint(effective_attack - 3, effective_attack + 5)
            m_hp -= p_dmg
            log_text += f"⚔️ Kamu menyerang **{m_name}** dan memberikan **{p_dmg} DMG**!\n"
            if m_hp <= 0:
                return await self.win_battle(interaction, m_hp)

            m_dmg = random.randint(m_atk - 3, m_atk + 3)
            hp -= m_dmg
            log_text += f"💥 **{m_name}** membalas dan memberikan **{m_dmg} DMG** kepadamu!\n"

        elif action == "defend":
            m_dmg = random.randint(m_atk - 3, m_atk + 3)
            reduced_dmg = max(1, int(m_dmg * 0.5))
            hp -= reduced_dmg
            
            log_text += f"🛡️ Kamu memasang perisai kokoh! Damage diredam 50%, hanya menerima **{reduced_dmg} DMG**.\n"
            
            if random.random() < 0.50:
                counter_dmg = max(5, int(effective_attack * 0.6))
                m_hp -= counter_dmg
                log_text += f"⚡ Berhasil! Kamu memancing celah dan melancarkan *Counter-Attack* sebesar **{counter_dmg} DMG** ke **{m_name}**!\n"
            else:
                log_text += f"💨 Kamu fokus bertahan penuh tanpa sempat menyerang balik.\n"
            
            if m_hp <= 0:
                return await self.win_battle(interaction, m_hp)

        self.monster["hp"] = m_hp
        
        if hp <= 0:
            return await self.lose_battle(interaction, gold)

        cursor.execute("UPDATE players SET hp = %s WHERE user_id = %s", (max(1, hp), user_id))
        conn.commit()

        self.player = (user_id, name, level, hp, max_hp, attack, gold, xp, hunger, pet_hunger, pet_attack, location)

        embed = discord.Embed(title=f"⚔️ Pertarungan Melawan: {m_name}", color=discord.Color.orange())
        if "Goblin" in m_name:
            embed.set_thumbnail(url="https://media.discordapp.net/attachments/1561653719970484304/1561660295758221352/goblin_1.png?ex=6ad728fc&is=6ad5d77c&hm=5e2ef5ddca01d5465ea08e8ba5da166ac5f2716ae9baa34ba5bd99f70b8e35b3&=&format=webp&quality=lossless")
        elif "Serigala" in m_name:
            embed.set_thumbnail(url="https://media.discordapp.net/attachments/1561653719970484304/1561659618978037850/wolf-head_1.png?ex=6ad7285b&is=6ad5d6db&hm=f600818d6f17084606a5ea2231cba7e9b55219fbd64ad3983169abc97f7593c3&=&format=webp&quality=lossless")
        elif "Kadal" in m_name or "Drake" in m_name:
            embed.set_thumbnail(url="https://media.discordapp.net/attachments/1561653719970484304/1561660746725720064/salamander.png?ex=6ad72968&is=6ad5d7e8&hm=31790d8f75925e68aa0a55d87fcbe147a25611194ef0bfb51bd4076f784a46da&=&format=webp&quality=lossless")
        else:
            embed.set_thumbnail(url="https://media.discordapp.net/attachments/1561653719970484304/1561660746725720064/salamander.png?ex=6ad72968&is=6ad5d7e8&hm=31790d8f75925e68aa0a55d87fcbe147a25611194ef0bfb51bd4076f784a46da&=&format=webp&quality=lossless")

        embed.add_field(name="HP Kamu", value=f"{hp}/{max_hp}", inline=True)
        embed.add_field(name="HP Musuh", value=f"{max(0, m_hp)}", inline=True)
        embed.description = log_text
        
        if not interaction.response.is_done():
            await interaction.response.edit_message(content="", embed=embed, view=self)
        else:
            await interaction.message.edit(content="", embed=embed, view=self)

    async def win_battle(self, interaction, m_hp):
        user_id = self.player[0]
        name, level, hp, max_hp, attack, gold, xp, hunger, pet_hunger, pet_attack, location = self.player[1:]
        
        gold += self.monster["gold"]
        xp += self.monster["xp"]
        new_hunger = max(0, hunger - 10)
        new_p_hunger = max(0, pet_hunger - 15)

        cursor.execute("UPDATE inventory SET durability = GREATEST(0, durability - 5) WHERE user_id = %s AND item_type IN ('weapon', 'armor')", (user_id,))
        
        drop_msg = ""
        if random.random() < 0.25:
            material = self.monster["drop"]
            cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = %s", (user_id, material))
            if cursor.fetchone():
                cursor.execute("UPDATE inventory SET quantity = quantity + 1 WHERE user_id = %s AND item_name = %s", (user_id, material))
            else:
                cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, %s, 'material', 1, 0, 100)", (user_id, material))
            drop_msg += f"\n💎 Menemukan material: **{material}**!"

        if "rare_drop" in self.monster and random.random() < 0.20:
            rare_item = self.monster["rare_drop"]
            cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = %s", (user_id, rare_item))
            if cursor.fetchone():
                cursor.execute("UPDATE inventory SET quantity = quantity + 1 WHERE user_id = %s AND item_name = %s", (user_id, rare_item))
            else:
                cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, %s, 'material', 1, 0, 100)", (user_id, rare_item))
            drop_msg += f"\n✨ **DROP LANGKA!** Mendapatkan **{rare_item}**!"

        lvl_msg = ""
        levels_gained = 0
        while xp >= get_xp_req(level):
            xp -= get_xp_req(level)
            level += 1
            max_hp += 25
            hp = max_hp
            attack += 5
            levels_gained += 1

        if levels_gained > 0:
            lvl_msg = f"\n\n✨ **LEVEL UP {levels_gained}x!** Naik ke level {level}!"

        cursor.execute('UPDATE players SET level = %s, hp = %s, max_hp = %s, attack = %s, gold = %s, xp = %s, hunger = %s, pet_hunger = %s WHERE user_id = %s', 
                       (level, hp, max_hp, attack, gold, xp, new_hunger, new_p_hunger, user_id))
        conn.commit()

        active_combats.discard(user_id)
        for child in self.children: child.disabled = True
        result_embed = discord.Embed(title=f"🎉 KEMENANGAN MEMBASMI {self.monster['name']}!", color=discord.Color.green())
        result_embed.description = f"Hadiah:\n🪙 +{self.monster['gold']} Gold\n✨ +{self.monster['xp']} XP{drop_msg}{lvl_msg}"
        
        next_view = ContinueHuntView(self.ctx)
        await interaction.response.edit_message(content="", embed=result_embed, view=next_view)
        self.stop()

    async def lose_battle(self, interaction, gold):
        user_id = self.player[0]
        penalty_gold = int(gold * 0.25)
        new_gold = max(0, gold - penalty_gold)
        
        cursor.execute("UPDATE players SET hp = 20, gold = %s WHERE user_id = %s", (new_gold, user_id))
        conn.commit()

        active_combats.discard(user_id)
        for child in self.children: child.disabled = True
        result_embed = discord.Embed(title="💀 KAMU TEWAS DI MEDAN PERANG!", color=discord.Color.dark_red())
        result_embed.description = f"Kamu dikalahkan oleh **{self.monster['name']}**!\nKehilangan **🪙 {penalty_gold} Gold** di dompet. HP dipulihkan ke 20."
        
        await interaction.response.edit_message(content="", embed=result_embed, view=self)
        self.stop()

# ----------------------------------------------------
# 4. SISTEM EKSPLORASI / WORLD MAP (!explore)
# ----------------------------------------------------
@bot.command(name="explore")
async def explore(ctx, *, wilayah: str = None):
    user_id = ctx.author.id
    cursor.execute("SELECT level, location FROM players WHERE user_id = %s", (user_id,))
    p = cursor.fetchone()
    if not p: return await ctx.send("Belum punya karakter!")
    level, current_loc = p
    
    zones = {
        "hutan pemula": {"name": "Hutan Pemula", "min_lv": 1},
        "gunung berapi": {"name": "Gunung Berapi", "min_lv": 5},
        "gua es kuno": {"name": "Gua Es Kuno", "min_lv": 10},
        "puncak naga berapi": {"name": "Puncak Naga Berapi", "min_lv": 15}
    }
    
    if not wilayah:
        embed = discord.Embed(title="🗺️ Peta Dunia (World Map)", description="Gunakan perintah `!explore <nama_wilayah>` (Contoh: `!explore puncak naga berapi`).", color=discord.Color.blue())
        embed.add_field(name="🌲 hutan pemula", value="• Syarat: Level 1+", inline=False)
        embed.add_field(name="🌋 gunung berapi", value="• Syarat: Level 5+", inline=False)
        embed.add_field(name="❄️ gua es kuno", value="• Syarat: Level 10+", inline=False)
        embed.add_field(name="🔥 puncak naga berapi (Map Sulit)", value="• Syarat: Level 15+ | Drop: Debu Bintang", inline=False)
        embed.add_field(name="📍 Lokasi Saat Ini", value=f"**{current_loc}**", inline=False)
        return await ctx.send(embed=embed)
        
    wilayah = wilayah.lower()
    if wilayah not in zones: return await ctx.send("❌ Wilayah tidak ditemukan!")
    
    target = zones[wilayah]
    if level < target["min_lv"]:
        return await ctx.send(f"⚠️ Level kamu terlalu rendah! Butuh **Level {target['min_lv']}** untuk memasuki wilayah ini.")
        
    cursor.execute("UPDATE players SET location = %s WHERE user_id = %s", (target["name"], user_id))
    conn.commit()
    await ctx.send(f"🗺️ Berhasil pindah ke wilayah: **{target['name']}**!")

# ----------------------------------------------------
# 5. SISTEM REPAIR DINAMIS (!repair)
# ----------------------------------------------------
@bot.command(name="repair")
async def repair(ctx):
    user_id = ctx.author.id
    cursor.execute("SELECT gold FROM players WHERE user_id = %s", (user_id,))
    p = cursor.fetchone()
    if not p: return await ctx.send("Belum punya karakter!")
    gold = p[0]
    
    cursor.execute("SELECT item_name, durability FROM inventory WHERE user_id = %s AND item_type IN ('weapon', 'armor')", (user_id,))
    gears = cursor.fetchall()
    
    if not gears: return await ctx.send("❌ Kamu tidak memiliki perlengkapan apapun untuk diperbaiki!")
    
    total_missing_durability = sum(100 - dur for _, dur in gears)
    if total_missing_durability <= 0:
        return await ctx.send("✨ Semua perlengkapanmu masih dalam kondisi prima (100% durability). Tidak perlu diperbaiki!")
    
    repair_cost = total_missing_durability
    if gold < repair_cost:
        return await ctx.send(f"❌ Gold di dompet tidak cukup! Butuh **🪙 {repair_cost} Gold**.")
        
    gold -= repair_cost
    cursor.execute("UPDATE players SET gold = %s WHERE user_id = %s", (gold, user_id))
    cursor.execute("UPDATE inventory SET durability = 100 WHERE user_id = %s AND item_type IN ('weapon', 'armor')", (user_id,))
    conn.commit()
    await ctx.send(f"🛠️ Pandai besi memperbaiki seluruh perlengkapanmu ke **100%**! Biaya: **🪙 {repair_cost} Gold**.")

# ----------------------------------------------------
# 6. SISTEM ENCHANT BERTAHAP & BERESIKO (!enchant)
# ----------------------------------------------------
@bot.command(name="enchant")
async def enchant(ctx, *, item_name: str = None):
    if not item_name:
        return await ctx.send("❌ Format salah! Gunakan: `!enchant <nama_item>`")
    
    user_id = ctx.author.id
    cursor.execute("SELECT gold FROM players WHERE user_id = %s", (user_id,))
    p = cursor.fetchone()
    if not p: return await ctx.send("Belum punya karakter!")
    gold = p[0]
    
    cursor.execute("SELECT item_name, item_type, quantity, enhance_level FROM inventory WHERE user_id = %s AND LOWER(item_name) = %s AND item_type IN ('weapon', 'armor')", (user_id, item_name.lower()))
    item = cursor.fetchone()
    
    if not item:
        return await ctx.send(f"❌ Item **'{item_name}'** tidak ditemukan di tasmu atau bukan jenis Equipment!")
    
    db_item_name, item_type, qty, enh = item
    if enh >= 10:
        return await ctx.send(f"🔥 Item **{db_item_name}** sudah mencapai batas maksimal enhance (**+10**)!")
    
    gold_cost = (enh + 1) * 75
    if gold < gold_cost:
        return await ctx.send(f"❌ Gold tidak cukup! Butuh **🪙 {gold_cost} Gold**.")
    
    success_rates = {0: 0.90, 1: 0.80, 2: 0.75, 3: 0.70, 4: 0.60, 5: 0.45, 6: 0.35, 7: 0.25, 8: 0.15, 9: 0.10}
    chance = success_rates.get(enh, 0.10)
    
    gold -= gold_cost
    cursor.execute("UPDATE players SET gold = %s WHERE user_id = %s", (gold, user_id))
    
    roll = random.random()
    if roll < chance:
        new_enh = enh + 1
        cursor.execute("UPDATE inventory SET enhance_level = %s WHERE user_id = %s AND item_name = %s", (new_enh, user_id, db_item_name))
        if item_type == 'weapon':
            cursor.execute("UPDATE players SET attack = attack + 6 WHERE user_id = %s", (user_id,))
            stat_msg = "+6 Attack"
        else:
            cursor.execute("UPDATE players SET max_hp = max_hp + 15, hp = hp + 15 WHERE user_id = %s", (user_id,))
            stat_msg = "+15 Max HP"
        conn.commit()
        await ctx.send(f"🎉 **ENCHANT BERHASIL!** **{db_item_name}** meningkat ke **+{new_enh}**! ({stat_msg}).")
    else:
        conn.commit()
        await ctx.send(f"💥 **ENCHANT GAGAL!** Usaha peningkatan **{db_item_name} (+{enh})** gagal dan gold hangus! (Peluang sukses: {int(chance*100)}%).")

# ----------------------------------------------------
# 7. SISTEM BUY DENGAN QUANTITY (!buy)
# ----------------------------------------------------
@bot.command(name="buy")
async def buy(ctx, *, args: str = None):
    if not args: 
        return await ctx.send("Format salah! Gunakan: `!buy <nama_item> [jumlah]`")
    
    user_id = ctx.author.id
    cursor.execute("SELECT gold FROM players WHERE user_id = %s", (user_id,))
    p = cursor.fetchone()
    if not p: return await ctx.send("Belum punya karakter!")
    
    gold = p[0]
    parts = args.strip().split()
    qty = 1
    
    if len(parts) > 1 and parts[-1].isdigit():
        qty = int(parts[-1])
        item_key = " ".join(parts[:-1]).lower()
    else:
        item_key = args.strip().lower()
        
    if qty <= 0: return await ctx.send("❌ Jumlah minimal 1!")
    
    current_hour = datetime.now().hour
    is_bm_open = 6 <= current_hour <= 23
    
    prices = {
        "potion": {"name": "Health Potion", "type": "potion", "price": 50, "market": False},
        "health potion": {"name": "Health Potion", "type": "potion", "price": 50, "market": False},
        "roti bakar": {"name": "Roti Bakar", "type": "food", "price": 30, "market": False},
        "roti": {"name": "Roti Bakar", "type": "food", "price": 30, "market": False},
        "tiket dungeon": {"name": "Tiket Dungeon", "type": "ticket", "price": 150, "market": False},
        "besi tua": {"name": "Besi Tua", "type": "material", "price": 120, "market": True},
        "taring serigala": {"name": "Taring Serigala", "type": "material", "price": 200, "market": True},
        "kristal sihir": {"name": "Kristal Sihir", "type": "material", "price": 500, "market": True}
    }
    
    if item_key not in prices: return await ctx.send("❌ Item tidak ditemukan!")
    info = prices[item_key]
    if info["market"] and not is_bm_open: return await ctx.send("❌ Black Market sedang tutup!")
    
    total_price = info["price"] * qty
    if gold < total_price: return await ctx.send(f"❌ Gold tidak cukup! Butuh **🪙 {total_price} Gold**.")
    
    gold -= total_price
    cursor.execute("UPDATE players SET gold = %s WHERE user_id = %s", (gold, user_id))
    
    cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = %s", (user_id, info["name"]))
    if cursor.fetchone():
        cursor.execute("UPDATE inventory SET quantity = quantity + %s WHERE user_id = %s AND item_name = %s", (qty, user_id, info["name"]))
    else:
        cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, %s, %s, %s, 0, 100)", (user_id, info["name"], info["type"], qty))
        
    conn.commit()
    await ctx.send(f"✅ Berhasil membeli **{qty}x {info['name']}** seharga **🪙 {total_price} Gold**!")

# ----------------------------------------------------
# 8. SISTEM CRAFTING (Termasuk Resep Spesial Baru)
# ----------------------------------------------------
@bot.command(name="craft")
async def craft(ctx, *, item: str = None):
    user_id = ctx.author.id
    if not item:
        embed = discord.Embed(title="⚒️ Meja Pandai Besi", color=discord.Color.dark_orange())
        embed.add_field(name="🪓 Pedang Mithril", value="• +25 Attack\n• Bahan: 3x Besi Tua, 2x Taring Serigala\n• Ketik: `!craft pedang mithril`", inline=False)
        embed.add_field(name="🦾 Armor Baja", value="• +60 Max HP\n• Bahan: 4x Besi Tua, 1x Kristal Sihir\n• Ketik: `!craft armor baja`", inline=False)
        embed.add_field(name="🛡️ Perisai Titan (BARU)", value="• +100 Max HP\n• Bahan: 5x Besi Tua, 3x Kristal Sihir, 1x Taring Serigala\n• Ketik: `!craft perisai titan`", inline=False)
        embed.add_field(name="🔱 Tombak Naga (BARU)", value="• +45 Attack\n• Bahan: 6x Taring Serigala, 3x Kristal Sihir, 1x Debu Bintang\n• Ketik: `!craft tombak naga`", inline=False)
        return await ctx.send(embed=embed)
    
    item = item.lower()
    if item in ["pedang mithril", "mithril"]:
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Besi Tua'", (user_id,))
        b = cursor.fetchone()
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Taring Serigala'", (user_id,))
        t = cursor.fetchone()
        if not b or b[0] < 3 or not t or t[0] < 2: return await ctx.send("❌ Material tidak cukup (Butuh: 3x Besi Tua, 2x Taring Serigala)!")
        
        cursor.execute("UPDATE inventory SET quantity = quantity - 3 WHERE user_id = %s AND item_name = 'Besi Tua'", (user_id,))
        cursor.execute("UPDATE inventory SET quantity = quantity - 2 WHERE user_id = %s AND item_name = 'Taring Serigala'", (user_id,))
        cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, 'Pedang Mithril', 'weapon', 1, 0, 100) ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + 1", (user_id,))
        cursor.execute("UPDATE players SET attack = attack + 25 WHERE user_id = %s", (user_id,))
        conn.commit()
        await ctx.send("🔥 Berhasil Crafting **Pedang Mithril** (+25 Attack)!")

    elif item in ["armor baja", "baja"]:
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Besi Tua'", (user_id,))
        b = cursor.fetchone()
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Kristal Sihir'", (user_id,))
        k = cursor.fetchone()
        if not b or b[0] < 4 or not k or k[0] < 1: return await ctx.send("❌ Material tidak cukup (Butuh: 4x Besi Tua, 1x Kristal Sihir)!")
            
        cursor.execute("UPDATE inventory SET quantity = quantity - 4 WHERE user_id = %s AND item_name = 'Besi Tua'", (user_id,))
        cursor.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = %s AND item_name = 'Kristal Sihir'", (user_id,))
        cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, 'Armor Baja', 'armor', 1, 0, 100) ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + 1", (user_id,))
        cursor.execute("UPDATE players SET max_hp = max_hp + 60, hp = hp + 60 WHERE user_id = %s", (user_id,))
        conn.commit()
        await ctx.send("🛡️ Berhasil Crafting **Armor Baja** (+60 Max HP)!")

    elif item in ["perisai titan", "titan"]:
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Besi Tua'", (user_id,))
        b = cursor.fetchone()
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Kristal Sihir'", (user_id,))
        k = cursor.fetchone()
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Taring Serigala'", (user_id,))
        t = cursor.fetchone()
        if not b or b[0] < 5 or not k or k[0] < 3 or not t or t[0] < 1: 
            return await ctx.send("❌ Material tidak cukup! Butuh: **5x Besi Tua, 3x Kristal Sihir, 1x Taring Serigala**.")
            
        cursor.execute("UPDATE inventory SET quantity = quantity - 5 WHERE user_id = %s AND item_name = 'Besi Tua'", (user_id,))
        cursor.execute("UPDATE inventory SET quantity = quantity - 3 WHERE user_id = %s AND item_name = 'Kristal Sihir'", (user_id,))
        cursor.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = %s AND item_name = 'Taring Serigala'", (user_id,))
        cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, 'Perisai Titan', 'armor', 1, 0, 100) ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + 1", (user_id,))
        cursor.execute("UPDATE players SET max_hp = max_hp + 100, hp = hp + 100 WHERE user_id = %s", (user_id,))
        conn.commit()
        await ctx.send("🛡️✨ Berhasil Crafting **Perisai Titan** legendaris (+100 Max HP)!")

    elif item in ["tombak naga", "tombak"]:
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Taring Serigala'", (user_id,))
        t = cursor.fetchone()
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Kristal Sihir'", (user_id,))
        k = cursor.fetchone()
        cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Debu Bintang'", (user_id,))
        d = cursor.fetchone()
        if not t or t[0] < 6 or not k or k[0] < 3 or not d or d[0] < 1: 
            return await ctx.send("❌ Material tidak cukup! Butuh: **6x Taring Serigala, 3x Kristal Sihir, 1x Debu Bintang**.")
            
        cursor.execute("UPDATE inventory SET quantity = quantity - 6 WHERE user_id = %s AND item_name = 'Taring Serigala'", (user_id,))
        cursor.execute("UPDATE inventory SET quantity = quantity - 3 WHERE user_id = %s AND item_name = 'Kristal Sihir'", (user_id,))
        cursor.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = %s AND item_name = 'Debu Bintang'", (user_id,))
        cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, 'Tombak Naga', 'weapon', 1, 0, 100) ON CONFLICT (user_id, item_name) DO UPDATE SET quantity = inventory.quantity + 1", (user_id,))
        cursor.execute("UPDATE players SET attack = attack + 45 WHERE user_id = %s", (user_id,))
        conn.commit()
        await ctx.send("🔱🔥 Berhasil Crafting **Tombak Naga** legendaris (+45 Attack)!")
    else:
        await ctx.send("❌ Resep item tidak dikenal! Ketik `!craft` untuk melihat daftar resep.")

# ----------------------------------------------------
# 9. SISTEM BANK (!bank)
# ----------------------------------------------------
@bot.command(name="bank")
async def bank(ctx, action: str = None, amount: int = 0):
    user_id = ctx.author.id
    cursor.execute("SELECT gold, bank_gold FROM players WHERE user_id = %s", (user_id,))
    p = cursor.fetchone()
    if not p: return await ctx.send("Belum punya karakter!")
    gold, bank_gold = p
    
    if action == "deposit" and amount > 0:
        if gold < amount: return await ctx.send("❌ Gold di dompet tidak cukup!")
        gold -= amount
        bank_gold += amount
        cursor.execute("UPDATE players SET gold = %s, bank_gold = %s WHERE user_id = %s", (gold, bank_gold, user_id))
        conn.commit()
        await ctx.send(f"🏦 Berhasil menabung **🪙 {amount} Gold**.")
    elif action == "withdraw" and amount > 0:
        if bank_gold < amount: return await ctx.send("❌ Saldo bank tidak cukup!")
        bank_gold -= amount
        gold += amount
        cursor.execute("UPDATE players SET gold = %s, bank_gold = %s WHERE user_id = %s", (gold, bank_gold, user_id))
        conn.commit()
        await ctx.send(f"🏦 Berhasil menarik **🪙 {amount} Gold**.")
    else:
        embed = discord.Embed(title="🏦 Bank Kota Sentral", description="• `!bank deposit <jumlah>`\n• `!bank withdraw <jumlah>`", color=discord.Color.blue())
        embed.add_field(name="Saldo Dompet", value=f"🪙 {gold}", inline=True)
        embed.add_field(name="Saldo Bank", value=f"🏦 {bank_gold}", inline=True)
        await ctx.send(embed=embed)

# ----------------------------------------------------
# 10. QUEST, EXPEDITION, SHOP, HUNT, REST, DUNGEON, HELP
# ----------------------------------------------------
bot.remove_command('help')

@bot.command(name="help")
async def help_command(ctx):
    is_owner = check_is_owner_ctx(ctx)
    
    embed = discord.Embed(title="📖 Daftar Perintah Bot", color=discord.Color.blue())
    
    user_commands = [
        "`!start` - Mendaftar karakter baru",
        "`!profile` - Melihat status karakter",
        "`!bag` / `!inventory` - Membuka tas & tombol item",
        "`!eat` - Makan Roti Bakar untuk memulihkan kelaparan",
        "`!hunt` - Berburu monster untuk mencari XP, Gold, & Material",
        "`!explore` - Pindah wilayah / map petualangan",
        "`!shop` - Melihat toko reguler & Black Market",
        "`!buy` - Membeli item dari toko",
        "`!craft` - Membuat senjata/armor spesial",
        "`!enchant` - Meningkatkan level enhance equipment",
        "`!repair` - Memperbaiki durability equipment",
        "`!rest` - Beristirahat untuk memulihkan HP",
        "`!quest` - Misi harian",
        "`!expedition` - Mengirim karakter ekspedisi",
        "`!dungeon` - Masuk ke dungeon bos (butuh tiket)",
        "`!bank` - Menabung atau menarik Gold",
        "`!material` - Panduan lokasi drop material monster"
    ]
    
    embed.add_field(name="🛡️ Perintah Petualang (User)", value="\n".join(user_commands), inline=False)
    
    if is_owner:
        admin_commands = [
            "`!adminaddgold @user <jumlah>`",
            "`!adminadditem @user <item> [jumlah]`",
            "`!adminsetlevel @user <level>`",
            "`!adminreset @user`"
        ]
        embed.add_field(name="⚡ Perintah Khusus Owner/Admin", value="\n".join(admin_commands), inline=False)
        
    await ctx.send(embed=embed)

@bot.command(name="quest")
async def quest(ctx):
    user_id = ctx.author.id
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT level, hp, max_hp, attack, gold, xp, last_quest FROM players WHERE user_id = %s", (user_id,))
    p = cursor.fetchone()
    if not p: return await ctx.send("Belum punya karakter!")
    level, hp, max_hp, attack, gold, xp, last_quest = p
    
    if last_quest == today:
        return await ctx.send("⏳ Kamu sudah mengambil Misi Harian hari ini. Kembalilah besok!")
        
    gold += 80
    xp += 75
    
    levels_gained = 0
    while xp >= get_xp_req(level):
        xp -= get_xp_req(level)
        level += 1
        max_hp += 25
        hp = max_hp
        attack += 5
        levels_gained += 1

    cursor.execute("UPDATE players SET level = %s, hp = %s, max_hp = %s, attack = %s, gold = %s, xp = %s, last_quest = %s WHERE user_id = %s", 
                   (level, hp, max_hp, attack, gold, xp, today, user_id))
    conn.commit()
    
    msg = f"📜 **Misi Selesai!** Hadiah: 🪙 +80 Gold, ✨ +75 XP."
    if levels_gained > 0:
        msg += f"\n✨ **LEVEL UP {levels_gained}x!** Naik ke level {level}!"
    await ctx.send(msg)

@bot.command(name="expedition")
@commands.cooldown(1, 300, commands.BucketType.user)
async def expedition(ctx):
    user_id = ctx.author.id
    cursor.execute("SELECT level, hp, max_hp, attack, gold, xp FROM players WHERE user_id = %s", (user_id,))
    p = cursor.fetchone()
    if not p: 
        ctx.command.reset_cooldown(ctx)
        return await ctx.send("Belum punya karakter!")
        
    level, hp, max_hp, attack, gold, xp = p
    reward_gold = random.randint(50, 150)
    reward_xp = random.randint(40, 100)
    
    gold += reward_gold
    xp += reward_xp
    
    levels_gained = 0
    while xp >= get_xp_req(level):
        xp -= get_xp_req(level)
        level += 1
        max_hp += 25
        hp = max_hp
        attack += 5
        levels_gained += 1

    cursor.execute("UPDATE players SET level = %s, hp = %s, max_hp = %s, attack = %s, gold = %s, xp = %s WHERE user_id = %s", 
                   (level, hp, max_hp, attack, gold, xp, user_id))
    conn.commit()
    
    msg = f"🧭 **Ekspedisi Selesai!** Hadiah: 🪙 +{reward_gold} Gold, ✨ +{reward_xp} XP."
    if levels_gained > 0:
        msg += f"\n✨ **LEVEL UP {levels_gained}x!** Naik ke level {level}!"
    await ctx.send(msg)

@bot.command(name="shop")
async def shop(ctx):
    current_hour = datetime.now().hour
    is_bm_open = 6 <= current_hour <= 23 
    
    embed = discord.Embed(title="🏛️ PUSAT PERBELANJAAN KOTA", description="Gunakan perintah `!buy <nama_item> [jumlah]`", color=discord.Color.gold())
    embed.add_field(name="🧪 TOKO REGULER", value="• potion: **50 Gold**\n• roti bakar: **30 Gold**\n• tiket dungeon: **150 Gold**", inline=False)
    
    bm_status = "🟢 **BUKA** (06:00 - 23:59)" if is_bm_open else "🔴 **TUTUP**"
    embed.add_field(name=f"🏴‍☠️ BLACK MARKET ({bm_status})", value="• besi tua: **120 Gold**\n• taring serigala: **200 Gold**\n• kristal sihir: **500 Gold**" if is_bm_open else "*Black Market sedang tutup.*", inline=False)
    await ctx.send(embed=embed)

async def trigger_hunt(ctx):
    user_id = ctx.author.id
    if user_id in active_combats:
        return await ctx.send("⚠️ Kamu sedang dalam pertempuran aktif!", delete_after=3)

    cursor.execute("SELECT user_id, name, level, hp, max_hp, attack, gold, xp, hunger, pet_hunger, pet_attack, location FROM players WHERE user_id = %s", (user_id,))
    player = cursor.fetchone()
    
    if not player: return await ctx.send("Belum punya karakter! Ketik `!start`.")
    if player[3] <= 20: return await ctx.send("⚠️ HP terlalu kritis! Pulihkan dengan `!eat` atau `!rest`.")

    active_combats.add(user_id)
    jeda_waktu = random.choice([2, 3, 4, 5, 6])
    
    msg = await ctx.send(f"🌲 Sedang menelusuri wilayah **{player[11]}**... *({jeda_waktu} detik)*")
    await sleep(jeda_waktu)

    level = player[2]
    location = player[11]

    hp_scaling = int(35 + (level * 18))
    atk_scaling = int(8 + (level * 2))

    if location == "Puncak Naga Berapi":
        hp_scaling = int(hp_scaling * 2.2)
        atk_scaling = int(atk_scaling * 1.8)
        monsters = [
            {"name": "🔥 Drake Abyssal", "hp": hp_scaling, "attack": atk_scaling, "gold": level * 20 + 40, "xp": level * 25 + 50, "drop": "Kristal Sihir", "rare_drop": "Debu Bintang"}
        ]
    elif location == "Gunung Berapi":
        hp_scaling = int(hp_scaling * 1.5)
        atk_scaling = int(atk_scaling * 1.3)
        monsters = [
            {"name": "Goblin Api", "hp": hp_scaling, "attack": atk_scaling, "gold": level * 10 + 20, "xp": level * 15 + 30, "drop": "Besi Tua"},
            {"name": "🔥 Raja Kadal Magma (Elite)", "hp": int(hp_scaling * 1.3), "attack": int(atk_scaling * 1.2), "gold": level * 25 + 50, "xp": level * 30 + 60, "drop": "Kristal Sihir"}
        ]
    elif location == "Gua Es Kuno":
        hp_scaling = int(hp_scaling * 1.8)
        atk_scaling = int(atk_scaling * 1.5)
        monsters = [
            {"name": "Elemental Es", "hp": hp_scaling, "attack": atk_scaling, "gold": level * 12 + 25, "xp": level * 18 + 35, "drop": "Taring Serigala"},
            {"name": "❄️ Yeti Raksasa Purba (Elite)", "hp": int(hp_scaling * 1.3), "attack": int(atk_scaling * 1.2), "gold": level * 30 + 70, "xp": level * 35 + 80, "drop": "Kristal Sihir"}
        ]
    else:
        monsters = [
            {"name": "Goblin Liar", "hp": hp_scaling, "attack": atk_scaling, "gold": level * 8 + 15, "xp": level * 12 + 20, "drop": "Besi Tua"},
            {"name": "Serigala Hitam", "hp": int(hp_scaling * 1.2), "attack": int(atk_scaling * 1.1), "gold": level * 10 + 20, "xp": level * 15 + 25, "drop": "Taring Serigala"}
        ]

    monster = random.choice(monsters)
    embed = discord.Embed(title=f"⚠️ PERTEMUAN LIAR: {monster['name']}", color=discord.Color.red())
    embed.description = f"Musuh muncul!\n**HP Musuh:** {monster['hp']}\n**Attack Musuh:** {monster['attack']}"
    embed.add_field(name="Sisa HP Kamu", value=f"{player[3]}/{player[4]}", inline=True)

    view = CombatView(ctx, player, monster)
    view.message = await msg.edit(content=None, embed=embed, view=view)

@bot.command(name="hunt")
@commands.cooldown(1, 5, commands.BucketType.user)
async def hunt(ctx):
    await trigger_hunt(ctx)

@bot.command(name="rest")
@commands.cooldown(1, 30, commands.BucketType.user)
async def rest(ctx):
    user_id = ctx.author.id
    cursor.execute("SELECT max_hp, hunger FROM players WHERE user_id = %s", (user_id,))
    p = cursor.fetchone()
    if not p: return await ctx.send("Belum punya karakter!")
    if p[1] <= 10: return await ctx.send("❌ Terlalu kelaparan! Makan dulu dengan `!eat`.")
    
    cursor.execute("UPDATE players SET hp = %s WHERE user_id = %s", (p[0], user_id))
    conn.commit()
    await ctx.send(f"⛺ Beristirahat. HP pulih menjadi {p[0]}!")

@bot.command(name="dungeon")
@commands.cooldown(1, 3600, commands.BucketType.user)
async def dungeon(ctx):
    user_id = ctx.author.id
    cursor.execute("SELECT name, level, hp, max_hp, attack, gold, xp, pet_name FROM players WHERE user_id = %s", (user_id,))
    player = cursor.fetchone()
    if not player: 
        ctx.command.reset_cooldown(ctx)
        return await ctx.send("Belum punya karakter!")
    name, level, hp, max_hp, attack, gold, xp, current_pet = player
    
    cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = 'Tiket Dungeon'", (user_id,))
    ticket = cursor.fetchone()
    if not ticket or ticket[0] < 1:
        ctx.command.reset_cooldown(ctx)
        return await ctx.send("⚠️ Butuh **1x Tiket Dungeon**!")
        
    cursor.execute("UPDATE inventory SET quantity = quantity - 1 WHERE user_id = %s AND item_name = 'Tiket Dungeon'", (user_id,))
    conn.commit()

    bosses = [
        {"name": "🐉 Dragon Penjaga Gua", "hp": 160, "attack": 32, "gold": 400, "xp": 250},
        {"name": "👑 Raja Orc Hitam", "hp": 130, "attack": 28, "gold": 300, "xp": 180}
    ]
    boss = random.choice(bosses)
    boss_hp, current_hp = boss["hp"], hp
    combat_log = f"🔥 **DUNGEON RAID** 🔥\nMenantang **{boss['name']}**!\n\n"
    
    while boss_hp > 0 and current_hp > 0:
        current_hp -= random.randint(boss["attack"] - 4, boss["attack"] + 4)
        if current_hp <= 0: break
        boss_hp -= random.randint(attack, attack + 12)

    pet_drop_msg = ""
    if current_hp <= 0:
        current_hp = 20
        combat_log += f"💀 **DUNGEON GAGAL!**"
    else:
        gold += boss["gold"]
        xp += boss["xp"]
        combat_log += f"🏆 **KEMENANGAN!** Hadiah: 🪙 +{boss['gold']} Gold, ✨ +{boss['xp']} XP."
        
        # ==========================================
        # SISTEM PET LANGKA DARI DUNGEON (CHANCE KECIL)
        # ==========================================
        roll = random.random()
        if roll < 0.05: # 5% Chance - Sangat Langka (Anak Naga Api)
            new_pet_name = "🔥 Anak Naga Api"
            bonus_atk = 30
            cursor.execute("UPDATE players SET pet_name = %s, pet_attack = %s, pet_hunger = 100 WHERE user_id = %s", (new_pet_name, bonus_atk, user_id))
            pet_drop_msg = f"\n\n🎁 **PET LEGENDARIS DIDAPATKAN!** Menemukan **{new_pet_name}** (+{bonus_atk} Atk) di sarang bos!"
        elif roll < 0.15: # 10% Chance berikutnya (Total 15%) - Langka (Serigala Salju Alpha)
            new_pet_name = "🐾 Serigala Salju Alpha"
            bonus_atk = 15
            cursor.execute("UPDATE players SET pet_name = %s, pet_attack = %s, pet_hunger = 100 WHERE user_id = %s", (new_pet_name, bonus_atk, user_id))
            pet_drop_msg = f"\n\n🎁 **PET LANGKA DIDAPATKAN!** Menemukan **{new_pet_name}** (+{bonus_atk} Atk) di dalam dungeon!"

        combat_log += pet_drop_msg
        
        levels_gained = 0
        while xp >= get_xp_req(level):
            xp -= get_xp_req(level)
            level += 1
            max_hp += 30
            current_hp = max_hp
            attack += 6
            levels_gained += 1
            
        if levels_gained > 0:
            combat_log += f"\n\n✨ **LEVEL UP {levels_gained}x!** Sekarang Level {level}!"

    cursor.execute('UPDATE players SET level = %s, hp = %s, max_hp = %s, attack = %s, gold = %s, xp = %s WHERE user_id = %s', 
                   (level, current_hp, max_hp, attack, gold, xp, user_id))
    conn.commit()
    await ctx.send(combat_log)

# ----------------------------------------------------
# 11. SISTEM PANDUAN MATERIAL (!material / !drop)
# ----------------------------------------------------
@bot.command(name="material", aliases=["materials", "drop", "guide"])
async def material_guide(ctx):
    embed = discord.Embed(
        title="📚 Panduan Lokasi Drop Material",
        description="Gunakan perintah `!explore <nama_wilayah>` untuk pindah lokasi berburu dan mencari material di bawah ini.",
        color=discord.Color.dark_purple()
    )
    embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3094/3094806.png")
    embed.add_field(name="🪨 Besi Tua", value="**Map:** Hutan Pemula & Gunung Berapi\n**Monster:** Goblin Liar & Goblin Api", inline=False)
    embed.add_field(name="🐺 Taring Serigala", value="• **Map:** Hutan Pemula & Gua Es Kuno\n• **Monster:** Serigala Hitam & Elemental Es", inline=False)
    embed.add_field(name="🔮 Kristal Sihir", value="• **Map:** Gunung Berapi, Gua Es Kuno & Puncak Naga Berapi\n• **Monster:** Raja Kadal Magma, Yeti Raksasa, Drake Abyssal", inline=False)
    embed.add_field(name="✨ Debu Bintang (Material Langka)", value="• **Map:** Puncak Naga Berapi (Syarat Level 15+)\n• **Monster:** Drake Abyssal (Peluang 20%)", inline=False)
    await ctx.send(embed=embed)

# ----------------------------------------------------
# 12. SISTEM ADMIN (DISEMBUNYIKAN DARI HELP BIASA)
# ----------------------------------------------------
@bot.command(name="adminreset")
async def adminreset(ctx, member: discord.Member = None):
    if not check_is_owner_ctx(ctx):
        return await ctx.send("❌ Perintah ini khusus untuk **Owner/Developer** bot!", delete_after=5)
    if not member:
        return await ctx.send("❌ Format salah! Gunakan: `!adminreset @nama_user`")
    
    cursor.execute("DELETE FROM players WHERE user_id = %s", (member.id,))
    cursor.execute("DELETE FROM inventory WHERE user_id = %s", (member.id,))
    conn.commit()
    await ctx.send(f"⚠️ **ADMIN ACTION:** Data karakter milik {member.mention} berhasil di-reset total oleh Owner!")

@bot.command(name="adminaddgold")
async def adminaddgold(ctx, member: discord.Member = None, amount: int = 0):
    if not check_is_owner_ctx(ctx):
        return await ctx.send("❌ Perintah ini khusus untuk **Owner/Developer** bot!", delete_after=5)
    if not member or amount <= 0:
        return await ctx.send("❌ Format salah! Gunakan: `!adminaddgold @user <jumlah_gold>`")
    
    cursor.execute("SELECT gold FROM players WHERE user_id = %s", (member.id,))
    p = cursor.fetchone()
    if not p:
        return await ctx.send(f"❌ {member.mention} belum memiliki karakter RPG!")
        
    new_gold = p[0] + amount
    cursor.execute("UPDATE players SET gold = %s WHERE user_id = %s", (new_gold, member.id))
    conn.commit()
    await ctx.send(f"🪙 **ADMIN SUCCESS:** Berhasil menambahkan **🪙 {amount} Gold** kepada {member.mention}! Total: **🪙 {new_gold}**.")

@bot.command(name="adminadditem")
async def adminadditem(ctx, member: discord.Member = None, *, item_args: str = None):
    if not check_is_owner_ctx(ctx):
        return await ctx.send("❌ Perintah ini khusus untuk **Owner/Developer** bot!", delete_after=5)
    if not member or not item_args:
        return await ctx.send("❌ Format salah! Gunakan: `!adminadditem @user <nama_item> [jumlah]`")
    
    parts = item_args.strip().split()
    qty = 1
    if parts[-1].isdigit():
        qty = int(parts[-1])
        item_name = " ".join(parts[:-1]).title()
    else:
        item_name = item_args.strip().title()

    cursor.execute("SELECT * FROM players WHERE user_id = %s", (member.id,))
    if not cursor.fetchone():
        return await ctx.send(f"❌ {member.mention} belum memiliki karakter RPG!")

    item_lower = item_name.lower()
    if "potion" in item_lower: itype = "potion"
    elif "roti" in item_lower or "food" in item_lower: itype = "food"
    elif "tiket" in item_lower: itype = "ticket"
    elif "pedang" in item_lower or "tombak" in item_lower or "kayu" in item_lower: itype = "weapon"
    elif "armor" in item_lower or "perisai" in item_lower or "baju" in item_lower: itype = "armor"
    else: itype = "material"

    cursor.execute("SELECT quantity FROM inventory WHERE user_id = %s AND item_name = %s", (member.id, item_name))
    if cursor.fetchone():
        cursor.execute("UPDATE inventory SET quantity = quantity + %s WHERE user_id = %s AND item_name = %s", (qty, member.id, item_name))
    else:
        cursor.execute("INSERT INTO inventory (user_id, item_name, item_type, quantity, enhance_level, durability) VALUES (%s, %s, %s, %s, 0, 100)", (member.id, item_name, itype, qty))
    
    conn.commit()
    await ctx.send(f"🎁 **ADMIN SUCCESS:** Berhasil memberikan **{qty}x {item_name}** ke tas {member.mention}!")

@bot.command(name="adminsetlevel")
async def adminsetlevel(ctx, member: discord.Member = None, target_level: int = 0):
    if not check_is_owner_ctx(ctx):
        return await ctx.send("❌ Perintah ini khusus untuk **Owner/Developer** bot!", delete_after=5)
    if not member or target_level <= 0:
        return await ctx.send("❌ Format salah! Gunakan: `!adminsetlevel @user <level_tujuan>`")
    
    cursor.execute("SELECT level FROM players WHERE user_id = %s", (member.id,))
    p = cursor.fetchone()
    if not p:
        return await ctx.send(f"❌ {member.mention} belum memiliki karakter RPG!")

    new_max_hp = 80 + ((target_level - 1) * 25)
    new_attack = 10 + ((target_level - 1) * 5)

    cursor.execute("UPDATE players SET level = %s, hp = %s, max_hp = %s, attack = %, xp = 0 WHERE user_id = %s", 
                   (target_level, new_max_hp, new_max_hp, new_attack, member.id))
    conn.commit()
    await ctx.send(f"⚡ **ADMIN SUCCESS:** Level {member.mention} diubah secara instan ke **Level {target_level}**! (HP: {new_max_hp}, Attack: {new_attack})")

# ==========================================
# ERROR HANDLERS
# ==========================================
@hunt.error
async def hunt_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Cooldown Berburu! Tunggu **{round(error.retry_after, 1)} detik** lagi.")

@rest.error
async def rest_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⛺ Cooldown Perkemahan! Tunggu **{round(error.retry_after, 1)} detik** lagi.")

@expedition.error
async def expedition_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Ekspedisi Berlangsung! Coba lagi dalam **{int(error.retry_after // 60)} menit**.")

@dungeon.error
async def dungeon_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Dungeon Terkunci! Coba lagi dalam **{int(error.retry_after // 60)} menit**.")

bot.run(DISCORD_TOKEN)