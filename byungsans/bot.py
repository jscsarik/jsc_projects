import discord
from discord.ext import commands
import asyncio
import random
import yt_dlp
from discord import FFmpegPCMAudio, PCMVolumeTransformer

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

FFMPEG_PATH = "ffmpeg"

asmr_links = [
    "https://youtu.be/f3FD8TLIZTY?si=iqGRi9vythtG7VwQ",
    "https://www.youtube.com/watch?v=HvsTfYVDlzI",
    "https://www.youtube.com/watch?v=AnpFfys-OwE",
    "https://youtu.be/rik9CNEKGow?si=S8I2R_ezwPGe5U64",
    "https://youtu.be/X1KQIIY_eFM?si=MCCiUpHTR9s_9E4p",
    "https://youtu.be/snYZYFmqv3Q?si=mJm8ZM0liyPyJMY4",
    "https://youtu.be/YfqmguKtx1E?si=WfRzYn3lbGtK3Of-",
    "https://www.youtube.com/watch?v=ytFUrodEd14"
]

music_queue = {}
is_playing = {}
is_asmr = {}

async def ensure_deaf(ctx):
    """봇이 음성 채널에 들어가면 귀를 막아 서버 자원을 아끼는 함수"""
    if ctx.voice_client:
        try:
            await ctx.guild.change_voice_state(channel=ctx.author.voice.channel, self_deaf=True)
        except:
            pass

@bot.command()
async def join(ctx):
    if ctx.author.voice:
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect(timeout=60, reconnect=True)
            await ensure_deaf(ctx) # 귀막기 적용
            await ctx.send("✅ **접속 완료!**")
        else:
            await ctx.send("이미 들어와 있습니다.")
    else:
        await ctx.send("먼저 음성채널에 들어가주세요.")

@bot.command()
async def play(ctx, *, url):
    if not ctx.author.voice:
        return await ctx.send("먼저 음성채널에 접속해주세요!")
    
    if not ctx.voice_client:
        try:
            await ctx.author.voice.channel.connect(timeout=60, reconnect=True)
            await ensure_deaf(ctx) # 귀막기 적용
        except:
            return await ctx.send("❌ 접속 실패! 잠시 후 다시 시도해주세요.")

    gid = ctx.guild.id
    
    if gid not in music_queue: music_queue[gid] = []
    if gid not in is_playing: is_playing[gid] = False
    if gid not in is_asmr: is_asmr[gid] = False

    music_queue[gid].append(url)
    
    if is_playing[gid] or is_asmr[gid]:
        await ctx.send(f"📥 **대기열 추가됨:** {url}")
    else:
        is_playing[gid] = True
        asyncio.create_task(재생_엔진(ctx, gid))
        await ctx.send(f"🔍 **검색 및 준비 중:** {url}")

async def 재생_엔진(ctx, gid):
    if is_asmr.get(gid):
        return

    if not music_queue.get(gid):
        is_playing[gid] = False
        await ctx.send("💤 **대기열이 비어서 쉽니다.**")
        return

    if not ctx.voice_client or not ctx.voice_client.is_connected():
        is_playing[gid] = False
        music_queue[gid] = []
        return
    
    url = music_queue[gid].pop(0)

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'no_warnings': True,
        'default_search': 'auto', 
        'source_address': '0.0.0.0', 
        'extractor_args': {'youtube': {'player_client': ['android', 'ios']}}
    }

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False))
        
        if not data:
            await ctx.send(f"⚠️ **검색 실패: {url}**")
            asyncio.create_task(재생_엔진(ctx, gid))
            return

        if 'entries' in data:
            data = data['entries'][0]
            
        stream_url = data['url']
        title = data.get('title', '노래')
        
        pcm = FFmpegPCMAudio(
            stream_url,
            executable=FFMPEG_PATH,
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn -bufsize 2048k -user_agent \"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36\""
        )
        source = PCMVolumeTransformer(pcm, volume=1.0)

        def _after(e):
            asyncio.run_coroutine_threadsafe(재생_엔진(ctx, gid), bot.loop)

        ctx.voice_client.play(source, after=_after)
        await ctx.send(f"▶️ **재생 중:** {title}")

    except Exception as e:
        print(f"에러: {e}")
        await ctx.send("❌ 오류 발생으로 다음 곡 넘어갑니다.")
        await asyncio.sleep(1) 
        asyncio.create_task(재생_엔진(ctx, gid))

@bot.command()
async def asmr(ctx):
    if not ctx.author.voice:
        return await ctx.send("먼저 음성채널에 접속해주세요!")
    
    if not ctx.voice_client:
        try:
            await ctx.author.voice.channel.connect(timeout=60, reconnect=True)
            await ensure_deaf(ctx)
        except:
            return await ctx.send("❌ 접속 실패!")

    gid = ctx.guild.id
    if gid not in music_queue: music_queue[gid] = []
    
    is_asmr[gid] = True
    is_playing[gid] = True 

    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
    
    url = random.choice(asmr_links)
    await ctx.send("🤫 **비밀 명령어 발견! ASMR 모드 시작** (노래는 잠시 멈춥니다)")
    
    ydl_opts = {
        'format': 'bestaudio/best', 
        'quiet': True,
        'source_address': '0.0.0.0',
        'extractor_args': {'youtube': {'player_client': ['android']}}
    }

    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False))
        stream_url = info['url']
        
        pcm = FFmpegPCMAudio(
            stream_url, 
            executable=FFMPEG_PATH,
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn -bufsize 2048k -user_agent \"Mozilla/5.0\""
        )
        
        def _after_asmr(e):
            is_asmr[gid] = False
            if music_queue.get(gid):
                asyncio.run_coroutine_threadsafe(재생_엔진(ctx, gid), bot.loop)
            else:
                is_playing[gid] = False
            print("ASMR 종료")

        ctx.voice_client.play(PCMVolumeTransformer(pcm), after=_after_asmr)

    except Exception as e:
        print(f"ASMR 에러: {e}")
        await ctx.send("❌ ASMR 로딩 실패!")
        is_asmr[gid] = False
        is_playing[gid] = False

# 💡 새롭게 추가된 24/7 무한 라디오 스트리밍 명령어!
@bot.command()
async def 무한(ctx):
    if not ctx.author.voice:
        return await ctx.send("🚨 먼저 음성 채널에 들어가 주세요!")

    if not ctx.voice_client:
        try:
            await ctx.author.voice.channel.connect(timeout=60, reconnect=True)
            await ensure_deaf(ctx)
        except:
            return await ctx.send("❌ 접속 실패!")
    elif ctx.voice_client.channel != ctx.author.voice.channel:
        await ctx.voice_client.move_to(ctx.author.voice.channel)

    gid = ctx.guild.id
    if gid not in music_queue: music_queue[gid] = []
    is_playing[gid] = True
    is_asmr[gid] = False

    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()

    await ctx.send("📻 **JSC 24/7 Radio** 온에어! 무한 송출을 시작합니다.")

    # 라디오 주소 (같은 서버이므로 localhost, 포트는 63010)
    radio_url = "http://localhost:63010/stream"
    
    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -bufsize 2048k'
    }

    try:
        pcm = FFmpegPCMAudio(radio_url, **FFMPEG_OPTIONS)
        
        def _after_muhan(e):
            # 라디오가 모종의 이유로 끊기면 대기열 재생으로 넘어가게 설정
            if music_queue.get(gid):
                asyncio.run_coroutine_threadsafe(재생_엔진(ctx, gid), bot.loop)
            else:
                is_playing[gid] = False

        ctx.voice_client.play(PCMVolumeTransformer(pcm, volume=1.0), after=_after_muhan)
        
    except Exception as e:
        print(f"라디오 스트리밍 에러: {e}")
        await ctx.send("❌ 라디오 송출에 실패했습니다.")

@bot.command()
async def skip(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("⏭️ **스킵!**")

@bot.command()
async def stop(ctx):
    vc = ctx.voice_client
    if vc:
        gid = ctx.guild.id
        music_queue[gid] = []
        is_playing[gid] = False
        is_asmr[gid] = False
        vc.stop()
        await vc.disconnect()
        await ctx.send("🛑 **종료!**")

@bot.command()
async def q(ctx):
    gid = ctx.guild.id
    queue = music_queue.get(gid, [])
    if not queue:
        await ctx.send("🗑️ **대기열 없음**")
    else:
        msg = "📜 **대기열:**\n" + "\n".join(f"{i+1}. {u}" for i, u in enumerate(queue))
        await ctx.send(msg)

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🤖 병sans 봇 명령어 안내", description="명령어를 입력해서 봇을 조종해 보세요!", color=discord.Color.blue())
    embed.add_field(name="`!play [노래제목/유튜브링크]`", value="노래를 재생하거나 대기열에 추가합니다.", inline=False)
    embed.add_field(name="`!무한`", value="📻 JSC 24/7 고음질 라디오 방송국을 무한 송출합니다.", inline=False)
    embed.add_field(name="`!q`", value="현재 대기열(예약된 노래 목록)을 확인합니다.", inline=False)
    embed.add_field(name="`!skip`", value="현재 재생 중인 곡을 넘깁니다.", inline=False)
    embed.add_field(name="`!stop`", value="재생을 종료하고 대기열을 비운 뒤 채널에서 퇴장합니다.", inline=False)
    embed.add_field(name="`!join`", value="봇을 현재 음성 채널에 부릅니다.", inline=False)
    
    # 💡 ASMR을 메뉴판에서 빼고, 하단 설명(footer)에 은밀하게 힌트만 남겼습니다.
    embed.set_footer(text="🤫 쉿... 잠이 오지 않는 밤을 위한 4글자짜리 비밀 명령어가 숨겨져 있습니다.")
    
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ 병Sans(플래그_보호막) 접속 완료: {bot.user}")

# ★★★ 디스코드 개발자 포털에서 '새로 발급받은 토큰'을 따옴표 안에 넣어주세요! ★★★
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

token = os.getenv("DISCORD_BOT_TOKEN")
if not token and os.path.exists("token.txt"):
    with open("token.txt", "r", encoding="utf-8") as f:
        token = f.read().strip()
if not token:
    token = os.getenv("BOT_TOKEN")

if not token:
    raise ValueError("디스코드 봇 토큰을 환경 변수(DISCORD_BOT_TOKEN) 또는 token.txt 파일에 설정해주세요.")

bot.run(token)