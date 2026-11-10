import discord
from discord.ext import commands
import asyncio
import random
import os
import time
import io

# 1. 봇 설정
PREFIX = '/' if os.name == 'nt' else '!'
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)
bot.remove_command('help')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg")
SUBWAY_BGM_DIR = os.path.join(BASE_DIR, "subway")
games = {}
detective_games = {}
DETECTIVE_MAP = {}
TRACK_MAP = []
track_games = {}

def load_detective_data():
    global DETECTIVE_MAP
    path = os.path.join(BASE_DIR, "탐정", "장소.txt")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) >= 2:
                        place = parts[0].strip()
                        words = [w.strip() for w in parts[1].split(",") if w.strip()]
                        DETECTIVE_MAP[place] = words
    except Exception as e:
        print(f"탐정 데이터 로드 중 오류: {e}")

def load_track_data():
    global TRACK_MAP
    path = os.path.join(BASE_DIR, "탐정", "stage.txt")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            TRACK_MAP = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"추적 탐정 데이터 로드 중 오류: {e}")


@bot.event
async def on_ready():
    load_detective_data()
    load_track_data()
    print(f'🔥 {bot.user.name} (스피드 모드 장착) 준비 완료!')
    print(f'   - 주제 파일: {os.listdir(os.path.join(BASE_DIR, "주제")) if os.path.exists(os.path.join(BASE_DIR, "주제")) else "폴더 없음!"}')

    # 봇 상태 메시지 설정
    activity = discord.Game(f"{PREFIX}help | 12종 미니게임")
    await bot.change_presence(status=discord.Status.online, activity=activity)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
        
    # [작업 지시 1: "역" 글자 예외 처리 (정답 인정 로직 강화)]
    # 노선도 게임 및 기타 역 이름 판별 시 끝에 "역"이 붙어 있다면 이를 제거하여 정답으로 인정
    content = message.content.strip()
    if content.endswith("역") and len(content) > 1:
        clean_content = content[:-1]
    else:
        clean_content = content
        
    # clean_content를 이용한 커스텀 판정 로직이 필요한 경우 여기에 추가될 수 있습니다.
    
    await bot.process_commands(message)

# ==========================================
# 🧩 도움말 및 종료 명령어
# ==========================================
@bot.command(name="help")
async def help(ctx):
    embed = discord.Embed(title="📜 서바이벌 봇 종합 도움말", description="사용 가능한 모든 명령어를 성격에 맞게 정리했습니다.\n\u200b", color=0x3498DB)
    
    embed.add_field(name="🎮 [게임 시작]", 
                    value=f"**`{PREFIX}주제어`** : 단어 릴레이 게임\n"
                          f"**`{PREFIX}라이어`** : 3라운드 마피아 게임\n"
                          f"**`{PREFIX}바보라이어`** : 블라인드 라이어 게임\n"
                          f"**`{PREFIX}텔레파시`** : 마음 예측 눈치 게임\n"
                          f"**`{PREFIX}제로섬`** : 흡혈 데스매치 심리전\n"
                          f"**`{PREFIX}양세찬 @유저`** : 팀전 눈치 핑퐁 게임\n"
                          f"**`{PREFIX}좀비런`** : 생존 눈치 추격전\n"
                          f"**`{PREFIX}비밀소설`** : 릴레이 추리 소설\n"
                          f"**`{PREFIX}군웅할거`** : 삼국지 천하통일 게임\n"
                          f"**`{PREFIX}탐정`** : 마피아 추리극\n"
                          f"**`{PREFIX}추적`** : 도주 경로 추적 마피아\n"
                          f"**`{PREFIX}노선도`** : 지하철 심리 추격전\n"
                          f"**`{PREFIX}랜덤`** : 무작위 게임 뽑기\n"
                          f"**`{PREFIX}영웅문`** : 영웅 경매 & 이적시장 거래\n\u200b", inline=False)
    
    embed.add_field(name="🛑 [게임 종료]", 
                    value=f"**`{PREFIX}종료`** : 현재 채널에서 진행 중인 **모든 게임**을 즉시 중단합니다.\n\u200b", inline=False)
    
    embed.add_field(name="🛠️ [게임별 특수 명령어]", 
                    value=f"**[양세찬]** `{PREFIX}정보`, `{PREFIX}정답 [단어]`, `{PREFIX}다음턴`\n"
                          f"　└ *(사회자용)* `{PREFIX}옐로카드`, `{PREFIX}레드카드`, `{PREFIX}정답인정`\n\n"
                          f"**[라이어류]** `{PREFIX}목록` (발언 기록), `{PREFIX}투표` (방장 조기 투표)\n\n"
                          f"**[군웅할거]** `{PREFIX}군웅스킵` (방장 턴 강제 스킵)\n\n"
                          f"**[탐정/추적]** `{PREFIX}탐정스킵` (방장 힌트 제출 스킵)\n"
                          f"**[영웅문]**\n"
                          f"• `{PREFIX}잔액` - 내 보유 자산(투자 자금)을 비공개로 확인합니다.\n"
                          f"• `{PREFIX}내역` - 경매 낙찰 및 유저 간 거래 자금 흐름을 비공개로 확인합니다.\n"
                          f"• `{PREFIX}스쿼드` - 현재 내가 보유한 영웅 목록과 포지션을 비공개로 확인합니다.\n\u200b", inline=False)

    embed.add_field(name="💡 [규칙 및 유틸리티]", 
                    value=f"**`{PREFIX}게임설명`** : 모든 게임의 승리 조건과 룰 확인\n"
                          f"**`{PREFIX}군웅할거룰`** : 삼국지 전투 연산 공식 확인\n"
                          f"**`{PREFIX}노선도능력`** : 지하철 특수 아이템 도감 확인\n"
                          f"**`{PREFIX}노선`** : 지하철 노선도 이미지 출력\n"
                          f"**`{PREFIX}help`** : 지금 보고 계신 도움말 메뉴 출력\n\u200b", inline=False)
    
    embed.add_field(name="🌐 추가 안내 및 설명서", 
                    value="🔗 **공식 웹사이트:** (https://juje-bot.vercel.app/)\n\u200b", inline=False)

    embed.set_footer(text="원하시는 게임의 명령어를 입력해 보세요! 숨겨진 기능도 있답니다 ✨")
    await ctx.send(embed=embed)

@bot.command(name="게임설명", aliases=["룰", "설명", "규칙"])
async def cmd_game_rules(ctx):
    embed = discord.Embed(title="🎮 서바이벌 봇 게임 규칙 안내", description="각 게임의 핵심 룰을 확인하고 최후의 승자가 되어보세요!", color=0x2ECC71)
    
    embed.add_field(name=f"🗣️ 주제어 서바이벌 (`{PREFIX}주제어`)", 
                    value="주어진 주제에 맞는 단어를 제한 시간 내에 입력하는 릴레이 게임입니다.\n"
                          "- **시간제한:** 기본 7초 (15턴이 넘어가면 **5초**로 단축!)\n"
                          "- 중복 단어는 금지되며, 제한 시간을 넘기면 즉시 탈락합니다.", inline=False)
    
    embed.add_field(name=f"🕵️ 3라운드 라이어 (`{PREFIX}라이어`)", 
                    value="시민들은 라이어를 찾고, 라이어는 정체를 숨기는 마피아형 게임입니다.\n"
                          "- **진행:** 총 3번의 발언과 3번의 처형 투표(80초)가 진행됩니다.\n"
                          "- **랜덤 처형:** 아무도 투표하지 않으면 **무작위로 한 명이 단상에 오릅니다!**\n"
                          "- **역전 찬스:** 라이어가 처형당해도 마지막에 제시어를 맞히면 라이어가 승리합니다.", inline=False)
    
    embed.add_field(name=f"🤡 바보 라이어 (`{PREFIX}바보라이어`)", 
                    value="모두가 제시어를 받지만 딱 한 명만 다른 단어를 받는 블라인드 라이어\n"
                          "- **진행:** 자신이 소수(바보)인지 다수(시민)인지 숨 막히는 눈치 게임!\n"
                          "- **블라인드:** 시민은 A 단어, 바보는 B 단어를 받으며 서로의 정체를 모른 채 시작합니다.\n"
                          "- **역전 찬스:** 바보가 처형당해도 시민들의 단어를 맞히면 바보가 승리합니다.", inline=False)
    
    embed.add_field(name=f"🤝 텔레파시 (`{PREFIX}텔레파시`)", 
                    value="주인공의 마음을 예측해서 살아남는 눈치 게임입니다.\n"
                          "- **목숨:** 시작 시 **하트 2개**가 주어집니다.\n"
                          "- 주인공의 선택과 내 예측이 다르면 하트가 1개 깎이며, 0이 되면 탈락합니다.", inline=False)
    
    embed.add_field(name=f"🩸 제로섬 데스매치 (`{PREFIX}제로섬`)", 
                    value="체력 5로 시작하는 가위바위보 상성 심리전입니다.\n"
                          "- **[공격]**: 지정한 상대의 체력을 흡수합니다. (+1/-1)\n"
                          "- **[방어]**: 공격을 튕겨내고 역으로 데미지를 줍니다. (단, 아무도 안 때리면 쫄보 페널티 -1)\n"
                          "- **[가드 크래시]**: 3인 이상 다수전 전용. 모두가 방어만 할 때 누르면 방어충들을 응징합니다!\n"
                          "- **[1대1]**: 2명만 남으면 비장한 BGM과 함께 [가드 부수기]가 포함된 3지선다 진검승부가 펼쳐집니다.", inline=False)
    
    embed.add_field(name=f"🦁 팀전 양세찬 게임 (`{PREFIX}양세찬 @유저`)", 
                    value="상대팀이 내 머리 위에 달아놓은 제시어를 맞히는 눈치 핑퐁 게임입니다!\n"
                          "- **진행:** 팝업창을 통해 상대팀 제시어를 비밀리에 설정한 후 릴레이로 진행됩니다.\n"
                          "- **핑퐁 룰:** 순서가 오면 [Step 1. 대답하기] ➡️ [Step 2. 질문하기] 순서로 티키타카를 주고받습니다.\n"
                          f"- **유틸리티:** `{PREFIX}정보`를 치면 우리 팀이 나눴던 공방 기록을 볼 수 있습니다.\n"
                          f"- **도전:** 턴에 상관없이 언제든 `{PREFIX}정답 [단어]`로 도전 가능! (틀리면 **팀 목숨** 1개 차감, 팀당 총 **5개**)\n"
                          f"- **👑 사회자 권한:** 지정된 사회자는 `{PREFIX}옐로카드`, `{PREFIX}레드카드`, `{PREFIX}정답인정`을 통해 게임의 신이 됩니다.", inline=False)
    
    embed.add_field(name=f"🧟 좀비 런 (`{PREFIX}좀비런`)", 
                    value="뒤에서 쫓아오는 좀비를 피해 다같이 숫자를 골라 전진하는 눈치 게임!\n"
                          "- **진행:** 매 라운드 3턴 동안 생존자들은 숫자를 눌러 누적 전진합니다.\n"
                          "- **발 꼬임:** 같은 숫자를 2명 이상 고르면 0칸 전진합니다!\n"
                          "- **추격:** 3턴 종료 후 좀비가 주사위를 굴려 따라오며, 잡히면 **플레이어 좀비**가 되어 같이 생존자를 쫓습니다.\n"
                          "- **포식/굶주림:** 매 라운드 한 명도 잡지 못하면 좀비의 굶주림(최대 3)이 올라 아사할 수 있습니다.", inline=False)
    
    embed.add_field(name=f"📖 비밀소설 (`{PREFIX}비밀소설`)", 
                    value="릴레이 소설의 결말만 보고 최초의 제시어를 맞히는 대환장 게임!\n"
                          "- **1번 타자:** 비밀 제시어를 보고 첫 문장을 씁니다.\n"
                          "- **2번 타자:** 첫 문장의 끝 30%만 보고 눈치껏 이어 씁니다.\n"
                          "- **추리자:** 스토리를 전혀 모른 채 마지막 문장과 4지선다 버튼만 보고 정답을 찍습니다!", inline=False)
    
    embed.add_field(name=f"🏯 삼국지: 군웅할거 (`{PREFIX}군웅할거`)", 
                    value="각 국가의 군주가 되어 12라운드 동안 외교와 전쟁을 펼칩니다.\n"
                          "- **외교:** 밀서를 보내 동맹을 맺거나 사신을 처형할 수 있습니다.\n"
                          "- **전쟁:** 병력을 방어/침략/육성으로 분배하여 적을 공격합니다.\n"
                          "- **스노우볼:** 수성에 성공한 육성 병력은 3배로 증식합니다!", inline=False)
    
    embed.add_field(name="🕵️‍♂️ [탐정 수사극]", 
                    value="**진행 방식 (최소 3인):**\n"
                          "1. 1명의 탐정과 N명의 범죄자로 나뉩니다.\n"
                          "2. 범죄자들은 특정 현장에 숨어 범죄명을 계획합니다.\n"
                          "3. 탐정이 수사할 현장을 지목하면, 그곳에 없는 다른 범죄자들이 '목격자'가 되어 익명 힌트를 제공합니다.\n"
                          "4. 탐정은 힌트를 조합해 해당 현장의 **[범인]**과 **[범죄명]**을 모두 맞혀야 승리합니다!", 
                    inline=False)
    
    embed.add_field(name=f"👣 추적 탐정 (`{PREFIX}추적`)", 
                    value="범죄자의 도주 경로를 쫓아가며 최종 위치와 범행을 맞히는 추적 마피아 게임입니다.\n"
                          "- **경로 추적:** 탐정은 1차 장소부터 시작해 힌트를 바탕으로 2차, 최종 은신처까지 쫓아가야 합니다.\n"
                          "- **단 한 번의 기회:** 추적 중 장소를 한 번이라도 잘못 짚으면 수사망이 뚫리며 즉시 패배합니다!\n"
                          "- **가짜 범죄명:** 범죄자는 탐정을 교란하기 위해 진짜 범죄와 가짜 범죄를 함께 제출합니다.\n"
                          "- **연쇄 검거:** 범죄자가 2명 이상일 경우, 첫 타겟을 잡더라도 남은 공범을 끝까지 추적해 전원 소탕해야 승리합니다.", 
                    inline=False)
    
    embed.add_field(name=f"🚇 지하철 심리 추격전 (`{PREFIX}노선도`)", 
                    value="도둑은 테러를, 형사는 도둑을 잡는 심리 추격전입니다.\n"
                          "- **진행:** 매 턴 모든 플레이어는 동시에 이동, 환승, 아이템 설치 등의 행동을 예약합니다.\n"
                          "- **승리 조건:** 도둑은 테러 장소에서 10턴간 버티거나, 형사가 오사하도록 유도하면 승리합니다. 형사는 도둑을 사살하면 승리합니다.\n"
                          "- **아이템:** 보급품 역에 도착하면 랜덤 아이템을 획득하며, 이를 활용해 서로의 위치를 추론하거나 방해할 수 있습니다.", 
                    inline=False)
    
    embed.add_field(name=f"⚔️ 영웅문 (`{PREFIX}영웅문`)", 
                    value="초기 자본 3,000만 원으로 영웅을 경매/거래하여 최강의 스쿼드를 꾸리는 전략 게임입니다.\n"
                          "- **진행:** [경매] ➔ [이적시장] 반복 (전체 라운드 중 25%는 영웅 2명이 나오는 더블 라운드!)\n"
                          "- **제한:** 영웅은 최대 4명 보유 가능, 모든 거래는 100만 원 단위 강제.\n"
                          "- **최종전:** 모든 라운드 종료 후, 내가 보유한 영웅 중 **주장 1명**과 **호위 최대 2명**을 직접 선택하여 출전시킵니다.\n"
                          "- **포지션 패널티:** [주장] 영웅은 주장 자리에, [호위] 영웅은 호위 자리에 가야 제 힘을 발휘합니다. 포지션이 어긋나면 최종전 스탯이 50% 삭감됩니다.\n"
                          "- ✔️ **총 능력치 (1점):** 벤치 영웅 제외! 실제 출전한 영웅(주장+호위)의 순수 스탯 합계 1위 유저.", 
                    inline=False)
    
    embed.add_field(name="❓ **설명만으로 부족하다면?**", 
                    value="아래 웹사이트에서 스크린샷과 함께 더 깔끔한 가이드를 보실 수 있습니다!\n🔗 https://juje-bot.vercel.app/", inline=False)

    embed.set_footer(text="더 궁금한 점이 있다면 언제든 물어보세요!")
    await ctx.send(embed=embed)

@bot.command(name="랜덤", aliases=["랜덤게임", "뽑기"])
async def cmd_random_game(ctx):
    game_list = [
        "주제어", "라이어", "바보라이어", "텔레파시", "제로섬",
        "양세찬", "좀비런", "비밀소설", "군웅할거", "탐정", "추적", "노선도", "영웅문"
    ]
    selected_game = random.choice(game_list)
    
    embed = discord.Embed(title="🎲 랜덤 게임 뽑기!", color=0x9B59B6)
    embed.description = f"두구두구두구...\n\n선택된 게임은 바로 **[{selected_game}]** 입니다! 🚀"
    if selected_game == "양세찬":
        embed.set_footer(text="💡 양세찬 게임이 당첨되어, 명령어를 입력한 유저가 자동으로 심판이 됩니다!")
        
    await ctx.send(embed=embed)
    await asyncio.sleep(1.5) # 결과 확인을 위한 짧은 대기 시간
    
    # 선택된 게임의 명령어 함수 직접 호출
    if selected_game == "주제어":
        await cmd_topic(ctx)
    elif selected_game == "라이어":
        await cmd_liar(ctx)
    elif selected_game == "바보라이어":
        await cmd_babo_liar(ctx)
    elif selected_game == "텔레파시":
        await cmd_telepathy(ctx)
    elif selected_game == "제로섬":
        await cmd_zerosum(ctx)
    elif selected_game == "양세찬":
        # 양세찬 게임은 심판 타겟이 필수이므로, 명령어를 친 사람(ctx.author)을 타겟으로 넘김
        await cmd_yang_se_chan(ctx, target=ctx.author)
    elif selected_game == "좀비런":
        await cmd_zombie_run(ctx)
    elif selected_game == "비밀소설":
        await cmd_secret_novel(ctx)
    elif selected_game == "군웅할거":
        await cmd_samguk(ctx)
    elif selected_game == "탐정":
        await cmd_detective(ctx)
    elif selected_game == "추적":
        await cmd_track(ctx)
    elif selected_game == "노선도":
        await cmd_subway(ctx)
    elif selected_game == "영웅문":
        await cmd_hero_market(ctx)

@bot.command(name="종료", aliases=["중단", "stop"])
async def cmd_stop_all(ctx):
    cid = ctx.channel.id
    count = 0
    if cid in games: del games[cid]; count += 1
    if cid in liar_games: del liar_games[cid]; count += 1
    if cid in babo_liar_games: del babo_liar_games[cid]; count += 1
    if cid in telepathy_games: del telepathy_games[cid]; count += 1
    if cid in zero_games: del zero_games[cid]; count += 1
    if cid in yang_se_chan_games: del yang_se_chan_games[cid]; count += 1
    if cid in zombie_games: del zombie_games[cid]; count += 1
    if cid in secret_novel_games: del secret_novel_games[cid]; count += 1
    if cid in samguk_games: del samguk_games[cid]; count += 1
    if cid in detective_games: del detective_games[cid]; count += 1
    if cid in track_games: del track_games[cid]; count += 1
    if cid in hero_market_games: del hero_market_games[cid]; count += 1

    
    if count > 0:
        await stop_sound(ctx)
        if ctx.voice_client: await ctx.voice_client.disconnect()
        await ctx.send("🛑 현재 채널의 모든 게임을 강제 종료했습니다.")
    else:
        await ctx.send("❌ 현재 진행 중인 게임이 없습니다.")

@bot.command(name="주제어종료")
async def cmd_stop_topic(ctx):
    cid = ctx.channel.id
    if cid in games:
        del games[cid]
        await stop_sound(ctx)
        if ctx.voice_client: await ctx.voice_client.disconnect()
        await ctx.send("🛑 주제어 게임을 강제 종료했습니다.")
    else: await ctx.send("❌ 진행 중인 주제어 게임이 없습니다.")

@bot.command(name="라이어종료")
async def cmd_stop_liar(ctx):
    cid = ctx.channel.id
    if cid in liar_games:
        del liar_games[cid]
        await stop_sound(ctx)
        if ctx.voice_client: await ctx.voice_client.disconnect()
        await ctx.send("🛑 라이어 게임을 강제 종료했습니다.")
    else: await ctx.send("❌ 진행 중인 라이어 게임이 없습니다.")

@bot.command(name="바보라이어종료")
async def cmd_stop_babo_liar(ctx):
    cid = ctx.channel.id
    if cid in babo_liar_games:
        del babo_liar_games[cid]
        await stop_sound(ctx)
        if ctx.voice_client: await ctx.voice_client.disconnect()
        await ctx.send("🛑 바보 라이어 게임을 강제 종료했습니다.")
    else: await ctx.send("❌ 진행 중인 바보 라이어 게임이 없습니다.")

@bot.command(name="텔레파시종료")
async def cmd_stop_telepathy(ctx):
    cid = ctx.channel.id
    if cid in telepathy_games:
        del telepathy_games[cid]
        await stop_sound(ctx)
        if ctx.voice_client: await ctx.voice_client.disconnect()
        await ctx.send("🛑 텔레파시 게임을 강제 종료했습니다.")
    else: await ctx.send("❌ 진행 중인 텔레파시 게임이 없습니다.")

@bot.command(name="제로섬종료")
async def cmd_stop_zero(ctx):
    cid = ctx.channel.id
    if cid in zero_games:
        del zero_games[cid]
        await stop_sound(ctx)
        if ctx.voice_client: await ctx.voice_client.disconnect()
        await ctx.send("🛑 제로섬 데스매치를 강제 종료했습니다.")
    else: await ctx.send("❌ 진행 중인 제로섬 데스매치가 없습니다.")




# ==========================================
# 🔊 소리 재생
# ==========================================
async def play_sound(ctx, filename):
    if not ctx.author.voice: return None
    channel = ctx.author.voice.channel
    
    if ctx.voice_client is None:
        vc = await channel.connect()
    else:
        vc = ctx.voice_client
        if vc.channel != channel:
            await vc.move_to(channel)
    
    ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg")
    file_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(file_path):
        if vc.is_playing(): vc.stop()
        vc.play(discord.FFmpegPCMAudio(file_path, executable=ffmpeg_path if os.path.exists(ffmpeg_path) else "ffmpeg"))
    return vc

async def stop_sound(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()

# ==========================================
# 🚀 게임 모집 (릴레이)
# ==========================================
class TopicJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=60.0)
        self.host = host
        self.players = [host]

    @discord.ui.button(label="🙋‍♂️ 참여하기", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        # [🛠️ 실시간 참가자 목록 업데이트]
        embed.description = f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n(최소 2명 필요)"
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🚀 게임시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 2:
            await interaction.response.send_message("최소 2명 이상의 참가자가 필요합니다!", ephemeral=True)
            return

        cid = interaction.channel.id
        if cid in games:
            await interaction.response.send_message("❌ 이미 진행 중인 게임이 있습니다.", ephemeral=True)
            return

        if not os.path.exists(os.path.join(BASE_DIR, "주제")) or not os.listdir(os.path.join(BASE_DIR, "주제")):
            await interaction.response.send_message("❌ '주제' 폴더가 비어있습니다.", ephemeral=True)
            return

        # 게임 테마 및 주제 선정
        file_list = [f for f in os.listdir(os.path.join(BASE_DIR, "주제")) if f.endswith(".txt")]
        selected_file = random.choice(file_list)
        topic_name = selected_file.replace('.txt', '')
        with open(os.path.join(BASE_DIR, "주제", selected_file), "r", encoding="utf-8") as f:
            raw_words = [line.strip() for line in f if line.strip()]
            valid_words = {w.replace(" ", ""): w for w in raw_words}

        games[cid] = {
            "status": "playing", "topic": topic_name, "valid_words": valid_words,
            "used_words": set(), "players": self.players, "scores": {p.name: 0 for p in self.players}
        }

        await interaction.response.edit_message(content=f"🚀 **[{topic_name}]** 게임을 시작합니다!", embed=None, view=None)
        await start_relay_game(await bot.get_context(interaction.message))
        self.stop()

@bot.command(name="주제어")
async def cmd_topic(ctx):
    if ctx.channel.id in games:
        await ctx.send(f"❌ 이미 진행 중입니다. `{PREFIX}중단`을 먼저 하세요.")
        return
    try: await play_sound(ctx, "intro.mp3")
    except: pass
    view = TopicJoinView(ctx.author)
    embed = discord.Embed(title="📢 주제어 퀴즈 모집", description=f"**현재 참가자:** {ctx.author.mention}\n(최소 2명 필요)", color=0xFFA500)
    await ctx.send(embed=embed, view=view)

# ==========================================
# ⚔️ 릴레이 게임 루프
# ==========================================
async def start_relay_game(ctx):
    cid = ctx.channel.id
    game = games[cid]
    game["status"] = "playing"
    players = game["players"]

    await stop_sound(ctx)
    await ctx.send(f"🚀 **게임 시작!** 주제: **[{game['topic']}]**\n순서대로 정답을 입력하세요!\n(15턴이 지나면 시간이 **5초**로 줄어듭니다!)")
    await asyncio.sleep(2)

    turn_idx = 0
    game_over = False

    while not game_over and cid in games:
        current_player = players[turn_idx % len(players)]
        
        if turn_idx >= 15:
            time_limit = 5.0
            msg_color = 0xFF0000 
            msg_extra = "🔥 **5초!! 서두르세요!!** 🔥"
        else:
            time_limit = 7.0
            msg_color = 0x00BFFF 
            msg_extra = f"**{int(time_limit)}초** 남았습니다!"

        try: await play_sound(ctx, "timer.mp3")
        except: pass

        embed = discord.Embed(
            title=f"👉 {current_player.name}님의 차례! (Turn {turn_idx + 1})",
            description=msg_extra,
            color=msg_color
        )
        await ctx.send(embed=embed)

        start_time = time.time()
        success = False 

        while True:
            elapsed = time.time() - start_time
            remaining = time_limit - elapsed

            if remaining <= 0:
                break

            def check(m):
                return m.channel == ctx.channel and m.author == current_player

            try:
                msg = await bot.wait_for('message', timeout=remaining, check=check)
                input_word = msg.content.replace(" ", "")

                if input_word in game["valid_words"]:
                    original = game["valid_words"][input_word]
                    score = len(original) * 10
                    game["scores"][current_player.name] += score
                    del game["valid_words"][input_word]
                    game["used_words"].add(original)
                    await msg.add_reaction("⭕")
                    await stop_sound(ctx) 
                    success = True
                    break 

                elif input_word in [w.replace(" ", "") for w in game["used_words"]]:
                    await msg.add_reaction("⚠️")

                else:
                    await msg.add_reaction("❌")

            except asyncio.TimeoutError:
                break 

        if success:
            turn_idx += 1 
            await asyncio.sleep(0.5)
        else:
            await stop_sound(ctx)
            await ctx.send(f"⏰ **시간 초과!**\n{current_player.name} 탈락! 게임 종료.")
            game_over = True

    await end_game(ctx, cid)

async def end_game(ctx, cid):
    if cid not in games: return
    game = games[cid]
    scores = game["scores"]
    del games[cid]

    if ctx.voice_client: await ctx.voice_client.disconnect()

    embed = discord.Embed(title="🏁 게임 종료!", color=0xFFD700)
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    for i, (name, score) in enumerate(sorted_scores):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "👤"
        embed.add_field(name=f"{medal} {name}", value=f"{score}점", inline=False)
    
    await ctx.send(embed=embed)

# 🕵️ 프리미엄 3라운드 라이어 게임 (Premium 3rd Liar Game)
# ==========================================
LIAR_TOPIC_DIR = os.path.join(BASE_DIR, "라이어주제")
liar_games = {}

# 모집 UI
class LiarJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=None)
        self.host = host
        self.players = [host]

    @discord.ui.button(label="🙋‍♂️ 참여하기", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        # [🛠️ 실시간 참가자 목록 업데이트]
        embed.description = f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n(최소 2명 필요)"
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"✅ 참여 완료! (현재 {len(self.players)}명)", ephemeral=True)

    @discord.ui.button(label="🚀 게임시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 2:
            await interaction.response.send_message("최소 2명 이상의 참가자가 필요합니다!", ephemeral=True)
            return

        cid = interaction.channel_id
        liar_games[cid] = {
            "status": "playing", "host": self.host, "players": self.players,
            "current_round": 1, "scores": {p.id: 0 for p in self.players},
            "p_names": {p.id: p.display_name for p in self.players},
            "descriptions": {p.id: [] for p in self.players},
            "liar": None, "word": "", "category": "",
            "votes": {}, "voted_users": set(), "defense_active": False, "caught": False
        }

        ctx = await bot.get_context(interaction.message)
        ctx.author = interaction.user
        await interaction.response.send_message("🎭 **3라운드 라이어 게임을 시작합니다!**")
        await start_liar_round(ctx, cid, 1)
        self.stop()

# 각 라운드 시작 로직 (40초 발언 시스템)
async def start_liar_round(ctx, cid, round_num):
    data = liar_games.get(cid)
    if not data: return
    data["current_round"] = round_num
    data["votes"] = {}
    data["voted_users"] = set()
    data["defense_active"] = False
    data["descriptions"] = {p.id: [] for p in data["players"]}
    data["late_waiters"] = set()
    
    if not os.path.exists(LIAR_TOPIC_DIR): os.makedirs(LIAR_TOPIC_DIR)
    files = [f for f in os.listdir(LIAR_TOPIC_DIR) if f.endswith(".txt")]
    if not files:
        await ctx.send("❌ '라이어주제' 폴더에 파일이 없습니다.")
        return

    target_file = random.choice(files)
    category = target_file.replace(".txt", "")
    try:
        with open(os.path.join(LIAR_TOPIC_DIR, target_file), "r", encoding="utf-8") as f:
            words = [l.strip() for l in f if l.strip()]
    except:
        await ctx.send("❌ 파일 읽기 오류!")
        return
    
    data["category"] = category
    data["word"] = random.choice(words)
    data["liar"] = random.choice(data["players"])

    # 🎵 라운드 시작 (liar.mp3 재생 전 이전 소리 강제 종료)
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
    try: await play_sound(ctx, "liar.mp3")
    except: pass

    for p in data["players"]:
        try:
            if p.id == data["liar"].id:
                await p.send(f"🕵️ **ROUND {round_num} - 당신은 [라이어]입니다!**\n주제: **[{category}]**\n다른 참가자들의 발언을 듣고 정체를 숨기세요!")
            else:
                await p.send(f"🙋 **ROUND {round_num} - 당신은 [시민]입니다!**\n주제: **[{category}]**\n제시어: **[{data['word']}]**")
        except: pass

    turn_order = random.sample(data["players"], len(data["players"]))
    data["turn_order"] = turn_order
    order_text = " -> ".join([p.name for p in turn_order])
    
    embed = discord.Embed(title=f"🏁 라이어 게임 - ROUND {round_num}", color=0xEE82EE)
    embed.add_field(name="🗂️ 카테고리", value=f"**{category}**", inline=False)
    embed.add_field(name="📢 발언 순서", value=order_text, inline=False)
    embed.description = "지금부터 순서대로 발언을 시작합니다.\n자신의 차례에 **40초** 내로 채팅을 입력하세요!"
    await ctx.send(embed=embed)

    while True:
        for p in turn_order:
            if cid not in liar_games: return 
            await ctx.send(f"👉 **{p.mention}**님의 차례입니다! (40초)")
            
            start_time = time.time()
            while True:
                remaining = 40.0 - (time.time() - start_time)
                if remaining <= 0:
                    await ctx.send(f"⏰ **{p.name}**님 시간 초과! (지각 가능 목록에 추가)")
                    data["descriptions"][p.id].append("(시간 초과)")
                    data["late_waiters"].add(p.id)
                    break

                def check(m):
                    return m.channel == ctx.channel and (m.author.id == p.id or m.author.id in data["late_waiters"])

                try:
                    msg = await bot.wait_for('message', timeout=remaining, check=check)
                    if msg.author.id == p.id:
                        await msg.add_reaction("✅")
                        data["descriptions"][p.id].append(msg.content)
                        break
                    else:
                        await msg.add_reaction("⌛")
                        data["descriptions"][msg.author.id].append(f"{msg.content} (발언권 늦음)")
                        data["late_waiters"].discard(msg.author.id)
                        # 현재 차례인 사람을 위해 루프 계속 (남은 시간 동안)
                except asyncio.TimeoutError:
                    await ctx.send(f"⏰ **{p.name}**님 시간 초과! (지각 가능 목록에 추가)")
                    data["descriptions"][p.id].append("(시간 초과)")
                    data["late_waiters"].add(p.id)
                    break
        
        if cid in liar_games:
            await ctx.send("📢 **모든 발언이 종료되었습니다! 즉시 투표를 시작합니다.**")
            result = await manage_liar_voting_loop(ctx, cid)
            if result == "ONE_MORE":
                await ctx.send("🏁 **'한 바퀴 더'가 결정되었습니다. 기존 순서대로 다시 발언을 시작합니다!**")
                if ctx.voice_client and ctx.voice_client.is_playing():
                    ctx.voice_client.stop()
                try: await play_sound(ctx, "liar.mp3")
                except: pass
                continue
            else:
                # 처형 완료 또는 투표 종료 시 answer_phase로 이동
                await start_answer_phase(ctx, cid)
                break

# 투표 UI (자동 종료 및 미투표자 표시 시스템)
class LiarVoteView(discord.ui.View):
    def __init__(self, ctx, players, cid, host):
        super().__init__(timeout=120.0)
        self.ctx = ctx
        self.players = players
        self.cid = cid
        self.host = host
        self.finished = False

        for p in players:
            btn = discord.ui.Button(label=p.display_name, style=discord.ButtonStyle.blurple)
            btn.callback = self.make_callback(p)
            self.add_item(btn)
        
        skip_btn = discord.ui.Button(label="[⏭️ 기권]", style=discord.ButtonStyle.secondary, row=4)
        skip_btn.callback = self.skip_callback
        self.add_item(skip_btn)
        
        onemore_btn = discord.ui.Button(label="[🔄 한 바퀴 더]", style=discord.ButtonStyle.primary, row=4)
        onemore_btn.callback = self.onemore_callback
        self.add_item(onemore_btn)

    async def on_timeout(self):
        if not self.finished:
            await self.ctx.send("⏰ **투표 시간이 종료되었습니다!**")
            self.finished = True
            self.stop()

    async def onemore_callback(self, interaction: discord.Interaction):
        data = liar_games.get(self.cid)
        if not data or interaction.user.id not in [p.id for p in self.players]: return
        if interaction.user.id in data["voted_users"]:
            await interaction.response.send_message("이미 투표했습니다!", ephemeral=True)
            return

        data["votes"]["one_more"] = data["votes"].get("one_more", 0) + 1
        data["voted_users"].add(interaction.user.id)
        await interaction.response.send_message("🔄 '한 바퀴 더'에 투표했습니다.", ephemeral=True)

        if len(data["voted_users"]) == len(self.players):
            if not self.finished:
                self.finished = True
                await interaction.message.edit(content="✅ **모든 참가자가 투표를 완료했습니다!**", view=None)
                self.stop()
        else:
            unvoted = [p.name for p in self.players if p.id not in data["voted_users"]]
            status_text = f"🗳️ **[투표 페이즈] 버튼을 클릭하세요! (2분)**\n현재 미투표자: **{', '.join(unvoted)}**"
            await interaction.message.edit(content=status_text, view=self)

    async def skip_callback(self, interaction: discord.Interaction):
        data = liar_games.get(self.cid)
        if not data or interaction.user.id not in [p.id for p in self.players]: return
        if interaction.user.id in data["voted_users"]:
            await interaction.response.send_message("이미 투표했습니다!", ephemeral=True)
            return

        # 'skip'을 특별 키로 하여 기권표 기록
        data["votes"]["skip"] = data["votes"].get("skip", 0) + 1
        data["voted_users"].add(interaction.user.id)
        await interaction.response.send_message("⏭️ 투표를 건너뛰었습니다 (기권).", ephemeral=True)

        if len(data["voted_users"]) == len(self.players):
            if not self.finished:
                self.finished = True
                await interaction.message.edit(content="✅ **모든 참가자가 투표를 완료했습니다!**", view=None)
                self.stop()
        else:
            unvoted = [p.name for p in self.players if p.id not in data["voted_users"]]
            status_text = f"🗳️ **[투표 페이즈] 버튼을 클릭하세요! (2분)**\n현재 미투표자: **{', '.join(unvoted)}**"
            await interaction.message.edit(content=status_text, view=self)

    def make_callback(self, target):
        async def callback(interaction: discord.Interaction):
            data = liar_games.get(self.cid)
            if not data or interaction.user.id not in [p.id for p in self.players]: return
            if interaction.user.id in data["voted_users"]:
                await interaction.response.send_message("이미 투표했습니다!", ephemeral=True)
                return

            data["votes"][target.id] = data["votes"].get(target.id, 0) + 1
            data["voted_users"].add(interaction.user.id)
            await interaction.response.send_message(f"✅ **{target.display_name}**님에게 투표했습니다!", ephemeral=True)

            if len(data["voted_users"]) == len(self.players):
                if not self.finished:
                    self.finished = True
                    await interaction.message.edit(content="✅ **모든 참가자가 투표를 완료했습니다!**", view=None)
                    self.stop()
            else:
                unvoted = [p.name for p in self.players if p.id not in data["voted_users"]]
                status_text = f"🗳️ **[투표 페이즈] 버튼을 클릭하세요! (2분)**\n현재 미투표자: **{', '.join(unvoted)}**"
                await interaction.message.edit(content=status_text, view=self)
        return callback

# 🔪 처형 투표 UI (죽이기 vs 살리기)
class LiarExecutionView(discord.ui.View):
    def __init__(self, ctx, voters, target_name, cid):
        super().__init__(timeout=40.0)
        self.ctx = ctx
        self.voters = voters
        self.target_name = target_name
        self.cid = cid
        self.kill_votes = 0
        self.save_votes = 0
        self.voted_users = set()

    @discord.ui.button(label="죽이기 🔪", style=discord.ButtonStyle.red)
    async def kill(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, True)

    @discord.ui.button(label="살리기 🕊️", style=discord.ButtonStyle.green)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, False)

    async def process_vote(self, interaction, is_kill):
        if interaction.user.id not in self.voters:
            await interaction.response.send_message("본인은 투표할 수 없거나 투표 권한이 없습니다.", ephemeral=True)
            return
        if interaction.user.id in self.voted_users:
            await interaction.response.send_message("이미 투표했습니다!", ephemeral=True)
            return
        
        self.voted_users.add(interaction.user.id)
        if is_kill: self.kill_votes += 1
        else: self.save_votes += 1
        
        await interaction.response.send_message(f"✅ 투표 완료! (현재 참여: {len(self.voted_users)}/{len(self.voters)})", ephemeral=True)
        
        data = liar_games.get(self.cid)
        unvoted_names = [data["p_names"][vid] for vid in self.voters if vid not in self.voted_users]

        if len(self.voted_users) < len(self.voters):
            status_text = f"🔪 **{self.target_name} 님을 처형하시겠습니까? (40초)**\n-# ⏳ 미투표자: {', '.join(unvoted_names)}"
            await interaction.message.edit(content=status_text, view=self)
        
        if len(self.voted_users) == len(self.voters):
            self.stop()

# 결과 및 처형 로직 시퀀스
# 최대 3차 투표 및 처형 관리 루프
async def manage_liar_voting_loop(ctx, cid):
    data = liar_games.get(cid)
    if not data: return
    
    for v_round in range(1, 4):
        # 매 투표 차수마다 데이터 초기화
        data["votes"] = {}
        data["voted_users"] = set()
        data["execution_result"] = None
        
        await ctx.send(f"🗳️ **[{v_round}차 투표 시작]** {v_round}차 지목 투표를 진행합니다.")
        
        # 1. 지목 투표 (버튼 UI)
        view = LiarVoteView(ctx, data["players"], cid, data["host"])
        unvoted = [p.name for p in data["players"]]
        vote_msg = await ctx.send(f"🗳️ **[투표 페이즈] {v_round}차 버튼을 클릭하세요! (2분)**\n현재 미투표자: **{', '.join(unvoted)}**", view=view)
        await view.wait()
        
        # 2. 투표 결과 집계
        res_msg = f"🗳️ **{v_round}차 투표 결과 발표**\n"
        for p in data["players"]:
            v = data["votes"].get(p.id, 0)
            res_msg += f"- {data['p_names'][p.id]}: {v}표\n"
        res_msg += f"- ⏭️ 기권: {data['votes'].get('skip', 0)}표\n"
        res_msg += f"- 🔄 한 바퀴 더: {data['votes'].get('one_more', 0)}표\n"
        await ctx.send(res_msg)

        # [🛠️ 수정] 건너뛰기 제외 플레이어 및 한바퀴더 투표 필터링
        player_votes = {k: v for k, v in data["votes"].items() if isinstance(k, int) and v > 0}
        onemore_v = data["votes"].get("one_more", 0)
        
        if not player_votes and onemore_v == 0:
            await ctx.send("🎲 **지목된 사람이 없거나 기권표가 많습니다. 시스템이 무작위로 한 명을 단상에 올립니다!**")
            target_id = random.choice([p.id for p in data["players"]])
            is_randomly_picked = True
        else:
            # 한 바퀴 더를 포함한 최다 득표자 선정
            max_v = max(max(player_votes.values() or [0]), onemore_v)
            top_candidates = []
            if onemore_v == max_v: top_candidates.append("one_more")
            for k, v in player_votes.items():
                if v == max_v: top_candidates.append(k)
            
            target_id = random.choice(top_candidates)
            is_randomly_picked = len(top_candidates) > 1

        if target_id == "one_more":
            await ctx.send("🔄 **'한 바퀴 더'가 최다 득표를 얻었습니다! 기존 순서대로 발언을 한 번 더 진행합니다!**")
            return "ONE_MORE"
            
        target_name = data["p_names"].get(target_id, "누군가")
        
        if is_randomly_picked:
            await ctx.send(f"🎲 **득표수가 같아 무작위로 {target_name}님이 지목되었습니다!**")
        else:
            await ctx.send(f"👉 투표 결과, 지목된 사람은 **{target_name}** 님입니다!")
            
        if v_round < 3:
            # ⚖️ 최후의 변론 시작 시 브금 교체 (judgment.mp3)
            if ctx.voice_client and ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            try: await play_sound(ctx, "judgment.mp3")
            except: pass

            # 최후의 변론 (40초)
            await ctx.send(f"⚖️ **최후의 변론** ({target_name}님, 40초)")
            def check_defense(m): return m.channel == ctx.channel and m.author.id == target_id
            try:
                await bot.wait_for('message', timeout=40.0, check=check_defense)
                await ctx.send(f"🎤 변론이 종료되었습니다.")
            except asyncio.TimeoutError:
                await ctx.send("⏰ 시간 초과! 변론이 종료되었습니다.")

            # 🔪 처형 찬반 투표
            voter_ids = [p.id for p in data["players"] if p.id != target_id]
            exec_view = LiarExecutionView(ctx, voter_ids, target_name, cid)
            unvoted_names = [data['p_names'][vid] for vid in voter_ids]
            await ctx.send(f"🔪 **{target_name} 님을 처형하시겠습니까? (40초)**\n-# ⏳ 미투표자: {', '.join(unvoted_names)}", view=exec_view)
            await exec_view.wait()
            
            # 결과 판정
            executed = exec_view.kill_votes > exec_view.save_votes
            res_msg = f"🗳️ **처형 투표 결과: {target_name}**\n- 죽이기: {exec_view.kill_votes}표 / 살리기: {exec_view.save_votes}표\n\n"

            if executed:
                res_msg += f"💥 **과반수가 찬성하여 {target_name}님이 처형되었습니다!**"
                await ctx.send(res_msg)
                await reveal_identity_and_set_caught(ctx, data, target_id, target_name)
                return "EXECUTED"
            else:
                res_msg += "🕊️ **살아남았습니다! 과반수의 동의를 얻지 못해 처형이 무산되었습니다.**"
                if v_round < 3:
                    res_msg += "\n🚨 **주의: 다음은 마지막 3차 투표입니다. 자비가 없습니다!**"
                await ctx.send(res_msg)
                continue
        else:
            await ctx.send("🚨 **3차 투표까지 왔습니다. 더 이상의 자비는 없습니다! 강제 처형을 집행합니다.**")
            await reveal_identity_and_set_caught(ctx, data, target_id, target_name)
            return "EXECUTED"
                
    return "FINISHED"

async def reveal_identity_and_set_caught(ctx, data, target_id, target_name):
    if target_id == data["liar"].id:
        await ctx.send(f"🚨 **속보: {target_name}님은 [라이어]였습니다!** 시민들의 승리가 눈앞입니다.")
        data["caught"] = True
    else:
        await ctx.send(f"😇 **속보: {target_name}님은 억울한 [시민]이었습니다!** 라이어는 살아남았습니다.")
        data["caught"] = False

async def start_answer_phase(ctx, cid):
    data = liar_games.get(cid)
    if not data: return
    data["defense_active"] = True
    liar = data["liar"]
    embed = discord.Embed(title="🛡️ 라이어의 최후의 역전 찬스", description=f"라이어: {liar.mention}", color=0xFF0000)
    embed.add_field(name="❓ 정답을 맞춰보세요 (2분)", value="지금 바로 **일반 채팅으로** 제시어를 입력하세요!", inline=False)
    await ctx.send(embed=embed)
    
    def check_ans(m):
        return m.channel == ctx.channel and m.author.id == liar.id
    
    try:
        # 라이어의 일반 채팅 입력을 기다림 (띄어쓰기 무시 판정)
        msg = await bot.wait_for('message', timeout=120.0, check=check_ans)
        is_correct = (msg.content.replace(" ", "") == data["word"].replace(" ", ""))
        await handle_liar_result(ctx, cid, is_correct)
    except asyncio.TimeoutError:
        if cid in liar_games and data.get("defense_active"):
            await handle_liar_result(ctx, cid, False)

async def handle_liar_result(ctx, cid, is_correct):
    data = liar_games.get(cid)
    if not data: return
    data["defense_active"] = False
    liar_id = data["liar"].id
    liar_caught = data.get("caught", False)
    liar_guessed_right = is_correct
    
    await ctx.send(f"🔍 **정답 공개: [{data['word']}]**")
    
    # 🏆 하이리스크 하이리턴 점수 계산
    if liar_caught:
        if not liar_guessed_right:
            res_msg = "🎉 **시민 완승!** 라이어는 정답도 모르고 잡혔습니다! (라이어 -100점 / 시민 전원 +100점)"
            data["scores"][liar_id] -= 100
            for p in data["players"]:
                if p.id != liar_id: data["scores"][p.id] += 100
        else:
            res_msg = "😱 **라이어 역전승!** 검거되었지만 제시어를 눈치챘습니다! (라이어 +100점)"
            data["scores"][liar_id] += 100
    else:
        if not liar_guessed_right:
            res_msg = "💦 **라이어 생존!** 하지만 정답은 몰랐네요! (라이어 +100점)"
            data["scores"][liar_id] += 100
        else:
            res_msg = "😈 **라이어 완승!** 완벽하게 속이고 정답까지 맞혔습니다! (라이어 +200점)"
            data["scores"][liar_id] += 200

    await ctx.send(res_msg)

    # 📈 현재 점수 현황 출력
    status_msg = "📈 **현재 점수 현황**\n"
    for p in data["players"]:
        status_msg += f"- {data['p_names'][p.id]}: {data['scores'][p.id]}점\n"
    await ctx.send(status_msg)
    
    await finish_round(ctx, cid)

async def finish_round(ctx, cid):
    data = liar_games.get(cid)
    if not data: return
    if data["current_round"] < 3:
        await ctx.send(f"➡️ **ROUND {data['current_round']} 종료.** 잠시 후 다음 라운드로 이동합니다.")
        await asyncio.sleep(5)
        await start_liar_round(ctx, cid, data["current_round"]+1)
    else:
        # 게임 종료 시 오디오 정지 및 연결 해제
        if ctx.voice_client:
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            await ctx.voice_client.disconnect()

        embed = discord.Embed(title="🏁 3라운드 게임 종료 - 최종 우승자 발표 🏁", color=0xFFD700)
        sorted_scores = sorted(data["scores"].items(), key=lambda x: x[1], reverse=True)
        winner_text = ""
        for i, (p_id, score) in enumerate(sorted_scores):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "👤"
            winner_text += f"{medal} **{data['p_names'][p_id]}**: {score}점\n"
        embed.description = winner_text
        await ctx.send(embed=embed)
        del liar_games[cid]

@bot.command(name="라이어")
async def cmd_liar(ctx):
    if ctx.channel.id in liar_games:
        await ctx.send("이미 게임이 진행 중입니다.")
        return
    try: await play_sound(ctx, "intro.mp3")
    except: pass
    view = LiarJoinView(ctx.author)
    await ctx.send(embed=discord.Embed(title="🕵️ 3라운드 라이어 게임 모집", description="참가자 대기 중... (최소 2인)", color=0xEE82EE), view=view)

@bot.command(name="목록")
async def cmd_list(ctx):
    cid = ctx.channel.id
    if cid in liar_games:
        data = liar_games[cid]
    elif cid in babo_liar_games:
        data = babo_liar_games[cid]
    else:
        return
        
    embed = discord.Embed(title=f"📢 ROUND {data['current_round']} 발언 기록", color=0x3498DB)
    for p in data.get("turn_order", data["players"]):
        descs = data["descriptions"].get(p.id, [])
        # [🛠️ 가독성 개선] 지각 발언이 있을 경우 '(시간 초과)'는 안 보이게 처리
        cleaned_descs = [d for d in descs if not (d == "(시간 초과)" and len(descs) > 1)]
        val = "\n".join([f"**•** {d}" for d in cleaned_descs]) if cleaned_descs else "(기록 없음)"
        embed.add_field(name=f"👤 {p.display_name}", value=val, inline=False)
    await ctx.send(embed=embed)

@bot.command(name="투표")
async def cmd_vote(ctx):
    cid = ctx.channel.id
    is_babo = False
    if cid in liar_games:
        data = liar_games[cid]
    elif cid in babo_liar_games:
        data = babo_liar_games[cid]
        is_babo = True
    else:
        return
        
    if data.get("defense_active"): return
    
    if ctx.author != data["host"]:
        await ctx.send("방장만 가능합니다!")
        return
    
    if is_babo:
        view = BaboVoteView(ctx, data["players"], cid, data["host"])
    else:
        view = LiarVoteView(ctx, data["players"], cid, data["host"])
        
    unvoted = [p.name for p in data["players"]]
    await ctx.send(f"🗳️ **[투표 페이즈] 버튼을 클릭하세요! (2분)**\n현재 미투표자: **{', '.join(unvoted)}**", view=view)


# ==========================================
# 🤡 바보 라이어 (Babo Liar Game - Blind Rule)
# ==========================================
babo_liar_games = {}

class BaboLiarJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=None)
        self.host = host
        self.players = [host]

    @discord.ui.button(label="🙋‍♂️ 참여하기", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        # [🛠️ 실시간 참가자 목록 업데이트]
        embed.description = f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n(최소 2명 필요)"
        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(f"✅ 참여 완료! (현재 {len(self.players)}명)", ephemeral=True)

    @discord.ui.button(label="🚀 게임시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 2:
            await interaction.response.send_message("최소 2명 이상의 참가자가 필요합니다!", ephemeral=True)
            return

        cid = interaction.channel_id
        babo_liar_games[cid] = {
            "status": "playing", "host": self.host, "players": self.players,
            "current_round": 1, "scores": {p.id: 0 for p in self.players},
            "p_names": {p.id: p.display_name for p in self.players},
            "descriptions": {p.id: [] for p in self.players},
            "liar": None, "word_main": "", "word_babo": "", "category": "",
            "votes": {}, "voted_users": set(), "defense_active": False, "caught": False
        }

        ctx = await bot.get_context(interaction.message)
        ctx.author = interaction.user
        await interaction.response.send_message("🎭 **바보 라이어 게임을 시작합니다! (블라인드 룰)**")
        await start_babo_round(ctx, cid, 1)
        self.stop()

async def start_babo_round(ctx, cid, round_num):
    data = babo_liar_games.get(cid)
    if not data: return
    data["current_round"] = round_num
    data["votes"] = {}
    data["voted_users"] = set()
    data["defense_active"] = False
    data["descriptions"] = {p.id: [] for p in data["players"]}
    data["late_waiters"] = set()
    
    if not os.path.exists(LIAR_TOPIC_DIR): os.makedirs(LIAR_TOPIC_DIR)
    files = [f for f in os.listdir(LIAR_TOPIC_DIR) if f.endswith(".txt")]
    if not files:
        await ctx.send("❌ '라이어주제' 폴더에 파일이 없습니다.")
        return

    target_file = random.choice(files)
    category = target_file.replace(".txt", "")
    try:
        with open(os.path.join(LIAR_TOPIC_DIR, target_file), "r", encoding="utf-8") as f:
            words = [l.strip() for l in f if l.strip()]
    except:
        await ctx.send("❌ 파일 읽기 오류!")
        return
    
    if len(words) < 2:
        await ctx.send("❌ 단어가 부족합니다. (최소 2개 필요)")
        return

    selected_words = random.sample(words, 2)
    data["category"] = category
    data["word_main"] = selected_words[0]
    data["word_babo"] = selected_words[1]
    data["liar"] = random.choice(data["players"])

    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
    try: await play_sound(ctx, "liar.mp3")
    except: pass

    for p in data["players"]:
        try:
            assigned_word = data["word_main"] if p.id != data["liar"].id else data["word_babo"]
            await p.send(f"🕵️ **당신의 제시어는 [{assigned_word}]입니다!**\n자신이 다수(시민)인지 소수(바보)인지 눈치껏 파악하며 발언하세요!")
        except: pass

    turn_order = random.sample(data["players"], len(data["players"]))
    data["turn_order"] = turn_order
    order_text = " -> ".join([p.name for p in turn_order])
    
    embed = discord.Embed(title=f"🤡 바보 라이어 - ROUND {round_num}", color=0xFFA500)
    embed.add_field(name="🗂️ 카테고리", value=f"**{category}**", inline=False)
    embed.add_field(name="📢 발언 순서", value=order_text, inline=False)
    embed.description = "지금부터 순서대로 발언을 시작합니다.\n자신의 차례에 **40초** 내로 채팅을 입력하세요!"
    await ctx.send(embed=embed)

    while True:
        for p in turn_order:
            if cid not in babo_liar_games: return 
            await ctx.send(f"👉 **{p.mention}**님의 차례입니다! (40초)")
            
            start_time = time.time()
            while True:
                remaining = 40.0 - (time.time() - start_time)
                if remaining <= 0:
                    await ctx.send(f"⏰ **{p.name}**님 시간 초과! (지각 가능 목록에 추가)")
                    data["descriptions"][p.id].append("(시간 초과)")
                    data["late_waiters"].add(p.id)
                    if cid not in babo_liar_games: return
                    break

                def check(m):
                    return m.channel == ctx.channel and (m.author.id == p.id or m.author.id in data["late_waiters"])

                try:
                    msg = await bot.wait_for('message', timeout=remaining, check=check)
                    if msg.author.id == p.id:
                        await msg.add_reaction("✅")
                        data["descriptions"][p.id].append(msg.content)
                        break
                    else:
                        await msg.add_reaction("⌛")
                        data["descriptions"][msg.author.id].append(f"{msg.content} (발언권 늦음)")
                        data["late_waiters"].discard(msg.author.id)
                except asyncio.TimeoutError:
                    await ctx.send(f"⏰ **{p.name}**님 시간 초과! (지각 가능 목록에 추가)")
                    data["descriptions"][p.id].append("(시간 초과)")
                    data["late_waiters"].add(p.id)
                    break
        
        if cid in babo_liar_games:
            await ctx.send("📢 **모든 발언이 종료되었습니다! 즉시 투표를 시작합니다.**")
            result = await manage_babo_voting_loop(ctx, cid)
            if result == "ONE_MORE":
                await ctx.send("🏁 **'한 바퀴 더'가 결정되었습니다. 기존 순서대로 다시 발언을 시작합니다!**")
                if ctx.voice_client and ctx.voice_client.is_playing():
                    ctx.voice_client.stop()
                try: await play_sound(ctx, "liar.mp3")
                except: pass
                continue
            else:
                await start_babo_answer_phase(ctx, cid)
                break

class BaboVoteView(discord.ui.View):
    def __init__(self, ctx, players, cid, host):
        super().__init__(timeout=120.0)
        self.ctx = ctx
        self.players = players
        self.cid = cid
        self.host = host
        self.finished = False

        for p in players:
            btn = discord.ui.Button(label=p.display_name, style=discord.ButtonStyle.blurple)
            btn.callback = self.make_callback(p)
            self.add_item(btn)
        
        skip_btn = discord.ui.Button(label="[⏭️ 기권]", style=discord.ButtonStyle.secondary, row=4)
        skip_btn.callback = self.skip_callback
        self.add_item(skip_btn)
        
        onemore_btn = discord.ui.Button(label="[🔄 한 바퀴 더]", style=discord.ButtonStyle.primary, row=4)
        onemore_btn.callback = self.onemore_callback
        self.add_item(onemore_btn)

    async def on_timeout(self):
        if not self.finished:
            await self.ctx.send("⏰ **투표 시간이 종료되었습니다!**")
            self.finished = True
            self.stop()

    async def onemore_callback(self, interaction: discord.Interaction):
        data = babo_liar_games.get(self.cid)
        if not data or interaction.user.id not in [p.id for p in self.players]: return
        if interaction.user.id in data["voted_users"]:
            await interaction.response.send_message("이미 투표했습니다!", ephemeral=True)
            return
        data["votes"]["one_more"] = data["votes"].get("one_more", 0) + 1
        data["voted_users"].add(interaction.user.id)
        await interaction.response.send_message("🔄 '한 바퀴 더'에 투표했습니다.", ephemeral=True)
        if len(data["voted_users"]) == len(self.players):
            if not self.finished:
                self.finished = True
                await interaction.message.edit(content="✅ **모든 참가자가 투표를 완료했습니다!**", view=None)
                self.stop()
        else:
            unvoted = [p.name for p in self.players if p.id not in data["voted_users"]]
            status_text = f"🗳️ **[투표 페이즈] 버튼을 클릭하세요! (2분)**\n현재 미투표자: **{', '.join(unvoted)}**"
            await interaction.message.edit(content=status_text, view=self)

    async def skip_callback(self, interaction: discord.Interaction):
        data = babo_liar_games.get(self.cid)
        if not data or interaction.user.id not in [p.id for p in self.players]: return
        if interaction.user.id in data["voted_users"]:
            await interaction.response.send_message("이미 투표했습니다!", ephemeral=True)
            return
        data["votes"]["skip"] = data["votes"].get("skip", 0) + 1
        data["voted_users"].add(interaction.user.id)
        await interaction.response.send_message("⏭️ 투표를 건너뛰었습니다 (기권).", ephemeral=True)
        if len(data["voted_users"]) == len(self.players):
            if not self.finished:
                self.finished = True
                await interaction.message.edit(content="✅ **모든 참가자가 투표를 완료했습니다!**", view=None)
                self.stop()
        else:
            unvoted = [p.name for p in self.players if p.id not in data["voted_users"]]
            status_text = f"🗳️ **[투표 페이즈] 버튼을 클릭하세요! (2분)**\n현재 미투표자: **{', '.join(unvoted)}**"
            await interaction.message.edit(content=status_text, view=self)

    def make_callback(self, target):
        async def callback(interaction: discord.Interaction):
            data = babo_liar_games.get(self.cid)
            if not data or interaction.user.id not in [p.id for p in self.players]: return
            if interaction.user.id in data["voted_users"]:
                await interaction.response.send_message("이미 투표했습니다!", ephemeral=True)
                return
            data["votes"][target.id] = data["votes"].get(target.id, 0) + 1
            data["voted_users"].add(interaction.user.id)
            await interaction.response.send_message(f"✅ **{target.display_name}**님에게 투표했습니다!", ephemeral=True)
            if len(data["voted_users"]) == len(self.players):
                if not self.finished:
                    self.finished = True
                    await interaction.message.edit(content="✅ **모든 참가자가 투표를 완료했습니다!**", view=None)
                    self.stop()
            else:
                unvoted = [p.name for p in self.players if p.id not in data["voted_users"]]
                status_text = f"🗳️ **[투표 페이즈] 버튼을 클릭하세요! (2분)**\n현재 미투표자: **{', '.join(unvoted)}**"
                await interaction.message.edit(content=status_text, view=self)
        return callback

class BaboExecutionView(discord.ui.View):
    def __init__(self, ctx, voters, target_name, cid):
        super().__init__(timeout=40.0)
        self.ctx = ctx
        self.voters = voters
        self.target_name = target_name
        self.cid = cid
        self.kill_votes = 0
        self.save_votes = 0
        self.voted_users = set()

    @discord.ui.button(label="죽이기 🔪", style=discord.ButtonStyle.red)
    async def kill(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, True)

    @discord.ui.button(label="살리기 🕊️", style=discord.ButtonStyle.green)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, False)

    async def process_vote(self, interaction, is_kill):
        if interaction.user.id not in self.voters:
            await interaction.response.send_message("본인은 투표할 수 없거나 투표 권한이 없습니다.", ephemeral=True)
            return
        if interaction.user.id in self.voted_users:
            await interaction.response.send_message("이미 투표했습니다!", ephemeral=True)
            return
        self.voted_users.add(interaction.user.id)
        if is_kill: self.kill_votes += 1
        else: self.save_votes += 1
        await interaction.response.send_message(f"✅ 투표 완료! (현재 참여: {len(self.voted_users)}/{len(self.voters)})", ephemeral=True)
        data = babo_liar_games.get(self.cid)
        unvoted_names = [data["p_names"][vid] for vid in self.voters if vid not in self.voted_users]
        if len(self.voted_users) < len(self.voters):
            status_text = f"🔪 **{self.target_name} 님을 처형하시겠습니까? (40초)**\n-# ⏳ 미투표자: {', '.join(unvoted_names)}"
            await interaction.message.edit(content=status_text, view=self)
        if len(self.voted_users) == len(self.voters):
            self.stop()

async def manage_babo_voting_loop(ctx, cid):
    data = babo_liar_games.get(cid)
    if not data: return
    for v_round in range(1, 4):
        data["votes"] = {}
        data["voted_users"] = set()
        await ctx.send(f"🗳️ **[{v_round}차 투표 시작]** {v_round}차 지목 투표를 진행합니다.")
        view = BaboVoteView(ctx, data["players"], cid, data["host"])
        unvoted = [p.name for p in data["players"]]
        await ctx.send(f"🗳️ **[투표 페이즈] {v_round}차 버튼을 클릭하세요! (2분)**\n현재 미투표자: **{', '.join(unvoted)}**", view=view)
        await view.wait()
        res_msg = f"🗳️ **{v_round}차 투표 결과 발표**\n"
        for p in data["players"]:
            v = data["votes"].get(p.id, 0)
            res_msg += f"- {data['p_names'][p.id]}: {v}표\n"
        res_msg += f"- ⏭️ 기권: {data['votes'].get('skip', 0)}표\n"
        res_msg += f"- 🔄 한 바퀴 더: {data['votes'].get('one_more', 0)}표\n"
        await ctx.send(res_msg)
        player_votes = {k: v for k, v in data["votes"].items() if isinstance(k, int) and v > 0}
        onemore_v = data["votes"].get("one_more", 0)
        if not player_votes and onemore_v == 0:
            await ctx.send("🎲 **지목된 사람이 없거나 기권표가 많습니다. 시스템이 무작위로 한 명을 단상에 올립니다!**")
            target_id = random.choice([p.id for p in data["players"]])
            is_randomly_picked = True
        else:
            max_v = max(max(player_votes.values() or [0]), onemore_v)
            top_candidates = []
            if onemore_v == max_v: top_candidates.append("one_more")
            for k, v in player_votes.items():
                if v == max_v: top_candidates.append(k)
            target_id = random.choice(top_candidates)
            is_randomly_picked = len(top_candidates) > 1
        if target_id == "one_more":
            await ctx.send("🔄 **'한 바퀴 더'가 최다 득표를 얻었습니다! 기존 순서대로 발언을 한 번 더 진행합니다!**")
            return "ONE_MORE"
        target_name = data["p_names"].get(target_id, "누군가")
        if is_randomly_picked: await ctx.send(f"🎲 **득표수가 같아 무작위로 {target_name}님이 지목되었습니다!**")
        await ctx.send(f"👉 투표 결과, 지목된 사람은 **{target_name}** 님입니다!")
        if v_round < 3:
            if ctx.voice_client and ctx.voice_client.is_playing(): ctx.voice_client.stop()
            try: await play_sound(ctx, "judgment.mp3")
            except: pass
            await ctx.send(f"⚖️ **최후의 변론** ({target_name}님, 40초)")
            def check_defense(m): return m.channel == ctx.channel and m.author.id == target_id
            try:
                await bot.wait_for('message', timeout=40.0, check=check_defense)
                await ctx.send(f"🎤 변론이 종료되었습니다.")
            except asyncio.TimeoutError:
                await ctx.send("⏰ 시간 초과! 변론이 종료되었습니다.")
            voter_ids = [p.id for p in data["players"] if p.id != target_id]
            exec_view = BaboExecutionView(ctx, voter_ids, target_name, cid)
            unvoted_names = [data['p_names'][vid] for vid in voter_ids]
            await ctx.send(f"🔪 **{target_name} 님을 처형하시겠습니까? (40초)**\n-# ⏳ 미투표자: {', '.join(unvoted_names)}", view=exec_view)
            await exec_view.wait()
            executed = exec_view.kill_votes > exec_view.save_votes
            res_msg = f"🗳️ **처형 투표 결과: {target_name}**\n- 죽이기: {exec_view.kill_votes}표 / 살리기: {exec_view.save_votes}표\n\n"
            if executed:
                res_msg += f"💥 **과반수가 찬성하여 {target_name}님이 처형되었습니다!**"
                await ctx.send(res_msg)
                await reveal_babo_identity(ctx, data, target_id, target_name)
                return "EXECUTED"
            else:
                res_msg += "🕊️ **살아남았습니다! 과반수의 동의를 얻지 못해 처형이 무산되었습니다.**"
                if v_round < 3: res_msg += "\n🚨 **주의: 다음은 마지막 3차 투표입니다. 자비가 없습니다!**"
                await ctx.send(res_msg)
                continue
        else:
            await ctx.send("🚨 **3차 투표까지 왔습니다. 더 이상의 자비는 없습니다! 강제 처형을 집행합니다.**")
            await reveal_babo_identity(ctx, data, target_id, target_name)
            return "EXECUTED"
    return "FINISHED"

async def reveal_babo_identity(ctx, data, target_id, target_name):
    if target_id == data["liar"].id:
        await ctx.send(f"🚨 **속보: {target_name}님은 [바보]였습니다!**")
        data["caught"] = True
    else:
        await ctx.send(f"😇 **속보: {target_name}님은 억울한 [시민]이었습니다!**")
        data["caught"] = False

async def start_babo_answer_phase(ctx, cid):
    data = babo_liar_games.get(cid)
    if not data: return
    data["defense_active"] = True
    liar = data["liar"]
    embed = discord.Embed(title="🛡️ 바보의 역전 찬스", description=f"바보: {liar.mention}", color=0xFF0000)
    embed.add_field(name="❓ 시민들의 단어를 맞춰보세요 (2분)", value="지금 바로 **일반 채팅으로** 단어를 입력하세요!", inline=False)
    await ctx.send(embed=embed)
    def check_ans(m): return m.channel == ctx.channel and m.author.id == liar.id
    try:
        msg = await bot.wait_for('message', timeout=120.0, check=check_ans)
        is_correct = (msg.content.replace(" ", "") == data["word_main"].replace(" ", ""))
        await handle_babo_result(ctx, cid, is_correct)
    except asyncio.TimeoutError:
        if cid in babo_liar_games and data.get("defense_active"):
            await handle_babo_result(ctx, cid, False)

async def handle_babo_result(ctx, cid, is_correct):
    data = babo_liar_games.get(cid)
    if not data: return
    data["defense_active"] = False
    liar_id = data["liar"].id
    liar_caught = data.get("caught", False)
    liar_guessed_right = is_correct
    await ctx.send(f"🔍 **정답 공개: 시민-[{data['word_main']}] / 바보-[{data['word_babo']}]**")
    if liar_caught:
        if not liar_guessed_right:
            res_msg = "🎉 **시민 완승!** 바보는 잡혔고 정답도 틀렸습니다! (바보 -100점 / 시민 전원 +100점)"
            data["scores"][liar_id] -= 100
            for p in data["players"]:
                if p.id != liar_id: data["scores"][p.id] += 100
        else:
            res_msg = "😱 **바보 역전승!** 검거되었지만 시민의 단어를 맞혔습니다! (바보 +100점)"
            data["scores"][liar_id] += 100
    else:
        if not liar_guessed_right:
            res_msg = "💦 **바보 생존!** 정체는 숨겼지만 정답은 몰랐네요! (바보 +100점)"
            data["scores"][liar_id] += 100
        else:
            res_msg = "😈 **바보 완승!** 완벽하게 속이고 정답까지 맞혔습니다! (바보 +200점)"
            data["scores"][liar_id] += 200
    await ctx.send(res_msg)
    if cid not in babo_liar_games: return
    status_msg = "📈 **현재 점수 현황**\n"
    for p in data["players"]: status_msg += f"- {data['p_names'][p.id]}: {data['scores'][p.id]}점\n"
    await ctx.send(status_msg)
    await finish_babo_round(ctx, cid)

async def finish_babo_round(ctx, cid):
    data = babo_liar_games.get(cid)
    if not data: return
    if data["current_round"] < 3:
        await ctx.send(f"➡️ **ROUND {data['current_round']} 종료.** 잠시 후 다음 라운드로 이동합니다.")
        await asyncio.sleep(5)
        await start_babo_round(ctx, cid, data["current_round"]+1)
    else:
        if ctx.voice_client:
            if ctx.voice_client.is_playing(): ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
        embed = discord.Embed(title="🏁 3라운드 바보 라이어 종료 - 최종 우승자 🏁", color=0xFFD700)
        sorted_scores = sorted(data["scores"].items(), key=lambda x: x[1], reverse=True)
        winner_text = ""
        for i, (p_id, score) in enumerate(sorted_scores):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "👤"
            winner_text += f"{medal} **{data['p_names'][p_id]}**: {score}점\n"
        embed.description = winner_text
        await ctx.send(embed=embed)
        del babo_liar_games[cid]

@bot.command(name="바보라이어")
async def cmd_babo_liar(ctx):
    if ctx.channel.id in babo_liar_games:
        await ctx.send("이미 게임이 진행 중입니다.")
        return
    try: await play_sound(ctx, "intro.mp3")
    except: pass
    view = BaboLiarJoinView(ctx.author)
    await ctx.send(embed=discord.Embed(title="🕵️ 바보 라이어 게임 모집", description="참가자 대기 중... (최소 2인)\n모두가 단어를 받지만 단 한 명만 다른 단어를 받는 블라인드 라이어!", color=0xFFA500), view=view)


# ==========================================
# 📡 텔레파시 게임 (Telepathy Game)
# ==========================================
telepathy_games = {}
TELEPATHY_FILE = os.path.join(BASE_DIR, "telepathy.txt")

class TelepathyJoinView(discord.ui.View):
    def __init__(self, host, target_hero):
        super().__init__(timeout=60.0)
        self.host = host
        self.target_hero = target_hero
        self.players = [host]

    @discord.ui.button(label="🙋‍♂️ 참여하기", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        # [🛠️ 실시간 참가자 목록 업데이트]
        embed.description = f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n(최소 2명 필요)"
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🚀 게임시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 2:
            await interaction.response.send_message("최소 2명 이상의 인원이 필요합니다!", ephemeral=True)
            return
        
        # 주인공 선정 로직 (수정: 멘션 우선, 미지정 시 랜덤)
        if self.target_hero:
            hero = self.target_hero
            if hero not in self.players: self.players.append(hero) # 주인공 합류 강제
        else:
            hero = random.choice(self.players)
        
        cid = interaction.channel.id
        telepathy_games[cid] = {
            "players": self.players, "hero": hero, "hp": {p.id: 2 for p in self.players if p.id != hero.id}, 
            "score": 0, "voted": {}, "questions": []
        }
        
        if os.path.exists(TELEPATHY_FILE):
            with open(TELEPATHY_FILE, "r", encoding="utf-8") as f:
                telepathy_games[cid]["questions"] = [l.strip() for l in f if "|" in l]

        # [🔊 BGM 교체 핵심 로직]
        ctx = await bot.get_context(interaction.message)
        if ctx.voice_client:
            ctx.voice_client.stop() # intro.mp3 즉시 중단
        
        try:
            await play_sound(ctx, "telepathy.mp3") # 텔레파시 브금 시작
        except:
            pass

        await interaction.response.edit_message(content="🎮 **텔레파시 게임을 시작합니다!**", embed=None, view=None)
        await start_telepathy_round(interaction.channel, cid)

# [1단계] 참가자들의 예측 투표 View
class TelepathyPredictView(discord.ui.View):
    def __init__(self, channel, cid, question, options):
        super().__init__(timeout=40.0)
        self.channel = channel
        self.cid = cid
        self.question = question
        self.options = options
        self.finished = False

        for opt in options:
            btn = discord.ui.Button(label=opt, style=discord.ButtonStyle.blurple)
            btn.callback = self.make_callback(opt)
            self.add_item(btn)

    def make_callback(self, choice):
        async def callback(interaction: discord.Interaction):
            data = telepathy_games.get(self.cid)
            if not data or interaction.user not in data["players"]: return
            
            # 주인공 우선 체크
            if interaction.user.id == data["hero"].id:
                await interaction.response.send_message("👑 주인공은 나중에 정답을 공개합니다! 잠시 기다려주세요.", ephemeral=True)
                return

            # 💀 탈락자 투표 방지
            if data["hp"][interaction.user.id] <= 0:
                await interaction.response.send_message("💀 이미 탈락하셨습니다! 관전해 주세요.", ephemeral=True)
                return

            if interaction.user.id in data["voted"]:
                await interaction.response.send_message("이미 투표했습니다!", ephemeral=True)
                return
                
            data["voted"][interaction.user.id] = choice
            await interaction.response.send_message(f"✅ 예측 완료: **[{choice}]**", ephemeral=True)
            
            # [🛠️ 실시간 생존자 및 미투표자 계산]
            alive_voters = [p.id for p in data["players"] if p.id != data["hero"].id and data["hp"][p.id] > 0]
            unvoted = [p.display_name for p in data["players"] if p.id in alive_voters and p.id not in data["voted"]]

            # 주인공 제외 '실제 생존자' 전원 투표 시 2단계로 전환
            if len(data["voted"]) == len(alive_voters):
                if not self.finished:
                    self.finished = True
                    await interaction.message.edit(content="✅ **친구들의 예측이 끝났습니다! 이제 주인공의 선택을 기다립니다.**", view=None)
                    await start_hero_choice_phase(self.channel, self.cid)
                    self.stop()
            else:
                # 미투표자 실시간 업데이트 (박제)
                status_text = f"-# ⏳ 미투표자: {', '.join(unvoted)}"
                await interaction.message.edit(content=status_text, view=self)
        return callback

# [2단계] 주인공의 정답 공개 View
class TelepathyHeroView(discord.ui.View):
    def __init__(self, channel, cid, options):
        super().__init__(timeout=40.0)
        self.channel = channel
        self.cid = cid
        self.finished = False

        for opt in options:
            btn = discord.ui.Button(label=opt, style=discord.ButtonStyle.green)
            btn.callback = self.make_callback(opt)
            self.add_item(btn)

    def make_callback(self, choice):
        async def callback(interaction: discord.Interaction):
            data = telepathy_games.get(self.cid)
            if not data: return
            
            # 오직 주인공만 누를 수 있음
            if interaction.user.id != data["hero"].id:
                await interaction.response.send_message("👑 이 버튼은 주인공만 누를 수 있습니다!", ephemeral=True)
                return
                
            if not self.finished:
                self.finished = True
                data["hero_answer"] = choice
                await interaction.response.defer() # [🛠️ 수정] 상호작용 지연 처리
                await interaction.message.delete()
                await process_telepathy_result(self.channel, self.cid)
                self.stop()
        return callback

async def start_telepathy_round(channel, cid):
    data = telepathy_games.get(cid)
    if not data or not data["questions"]:
        await channel.send("❌ 'telepathy.txt' 파일이 없거나 질문 내용이 없습니다! 게임을 종료합니다.")
        if cid in telepathy_games: del telepathy_games[cid]
        return
    line = random.choice(data["questions"])
    question, opts = line.split("|")
    options = [opt.strip() for opt in opts.split(",")]
    
    data["voted"] = {}
    data["current_q"] = question
    data["current_opts"] = options
    
    # [📊 실시간 생존자 수 계산]
    alive_voters = [p.id for p in data["players"] if p.id != data["hero"].id and data["hp"][p.id] > 0]
    unvoted_names = [p.display_name for p in data["players"] if p.id in alive_voters]
    
    embed = discord.Embed(title="❓ 텔레파시 퀴즈 (예측 단계)", 
                          description=f"👉 주인공({data['hero'].mention})을 제외한 분들은 주인공의 마음을 예측해서 투표하세요!\n\n**질문: {question}**", 
                          color=0x3498DB)
    # [🛠️ 푸터 수정: 개인별 HP 시스템 반영]
    embed.set_footer(text=f"👥 남은 생존자: {len(alive_voters) + 1}명 | 최후의 1인이 승리합니다!")
    await channel.send(content=f"-# ⏳ 미투표자: {', '.join(unvoted_names)}", embed=embed, view=TelepathyPredictView(channel, cid, question, options))

async def start_hero_choice_phase(channel, cid):
    data = telepathy_games.get(cid)
    if not data: return
    
    embed = discord.Embed(title="👑 주인공의 선택 (정답 공개)", 
                          description=f"친구들의 예측이 끝났습니다! 이제 **주인공({data['hero'].mention})**이 진짜 마음을 고를 차례입니다!", 
                          color=0x2ECC71)
    await channel.send(embed=embed, view=TelepathyHeroView(channel, cid, data["current_opts"]))

async def process_telepathy_result(channel, cid):
    data = telepathy_games.get(cid)
    if not data: return
    
    hero_answer = data.get("hero_answer")
    voted = data.get("voted", {})
    
    # 1. 결과 텍스트 생성 및 HP 차감
    res_text = f"👑 **주인공의 진짜 마음: [{hero_answer}]**\n\n"
    eliminated_mentions = []
    
    for uid, choice in voted.items():
        user = channel.guild.get_member(uid)
        name = user.display_name if user else "퇴장한 유저"
        
        if choice == hero_answer:
            status = "✅ 통과"
        else:
            status = "❌ 실패"
            data["hp"][uid] -= 1 # HP 차감
            if data["hp"][uid] <= 0:
                eliminated_mentions.append(f"💀 **{name}** 탈락!")
        
        hp_bar = "❤️" * data["hp"][uid] if data["hp"][uid] > 0 else "💀"
        res_text += f"- **{name}**: {choice} ({status}) | {hp_bar}\n"

    embed = discord.Embed(title="📊 라운드 결과 발표", description=res_text, color=0xF1C40F)
    await channel.send(embed=embed)
    
    # 2. 탈락자 실시간 멘트 출력
    for ment in eliminated_mentions:
        survivors_count = len([uid for uid, hp in data["hp"].items() if hp > 0])
        await channel.send(f"{ment} 남은 생존자: **{survivors_count}명**")

    # 3. [🛠️ 버그 픽스] 승리/종료 조건 체크 (우승자 멘션 100% 보장)
    survivors_ids = [uid for uid, hp in data["hp"].items() if hp > 0]
    survivor_count = len(survivors_ids)

    if survivor_count <= 1:
        if survivor_count == 1:
            winner_id = survivors_ids[0]
            # [핵심] 주인공(hero)을 제외한 실제 플레이어 리스트에서 최후의 1인 객체 추출
            winner = next((p for p in data["players"] if p.id == winner_id), None)
            
            if winner:
                winner_mention = winner.mention # @유저 멘션 적용
            else:
                winner_mention = f"<@{winner_id}>"

            final_embed = discord.Embed(
                title="🏆 TELEPATHY MASTER",
                description=f"🏆 축하합니다! 최후의 통과자 {winner_mention}님이 텔레파시 마스터로 등극했습니다!",
                color=0xFFD700
            )
            await channel.send(embed=final_embed)
        else:
            if cid not in telepathy_games: return
            await channel.send("💀 모든 참가자가 탈락했습니다! (우승자 없음)")
        
        # BGM 정지 및 데이터 삭제 (게임 종료)
        if channel.guild.voice_client:
            channel.guild.voice_client.stop()
        if cid in telepathy_games:
            del telepathy_games[cid]
        return

    # 4. [🛠️ 자동 진행] 4초 대기 후 즉시 다음 라운드 시작
    await channel.send("⏳ **잠시 후 다음 라운드가 자동으로 시작됩니다...**")
    await asyncio.sleep(4)
    
    if cid in telepathy_games:
        await start_telepathy_round(channel, cid)

@bot.command(name="텔레파시")
async def cmd_telepathy(ctx, target: discord.Member = None):
    if ctx.channel.id in telepathy_games: return
    try: await play_sound(ctx, "intro.mp3")
    except: pass
    view = TelepathyJoinView(ctx.author, target)
    embed = discord.Embed(title="🤝 텔레파시 게임 모집", description=f"**현재 참가자:** {ctx.author.mention}\n(최소 2명 필요)", color=0x9B59B6)
    if target: embed.add_field(name="👑 선정된 주인공", value=target.mention)
    await ctx.send(embed=embed, view=view)

# ==========================================
# 🩸 제로섬 데스매치 (Zero-Sum Deathmatch)
# ==========================================
zero_games = {}

class ZeroJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=60.0)
        self.host = host
        self.players = [host]

    @discord.ui.button(label="🙋‍♂️ 참여하기", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        # [🛠️ 실시간 참가자 목록 업데이트]
        embed.description = f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n(최소 2명 필요)"
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🚀 게임시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 2:
            await interaction.response.send_message("최소 2인 이상이 필요합니다!", ephemeral=True)
            return

        cid = interaction.channel.id
        zero_games[cid] = {
            "players": self.players,
            "hp": {p.id: 5 for p in self.players},
            "p_names": {p.id: p.display_name for p in self.players},
            "actions": {},
            "round": 1,
            "debuffs": set(), # [NEW] 가드 크래시로 인해 방어가 봉인된 유저들
            "bgm_elapsed": 0,
            "bgm_start": time.time()
        }
        
        # [🛠️ 수정 2] 브금 전환 (intro 종료 후 zero 재생)
        ctx = await bot.get_context(interaction.message)
        ctx.author = interaction.user # 방장 기준
        if ctx.voice_client:
            ctx.voice_client.stop()
        try: await play_sound(ctx, "zero.mp3")
        except: pass

        await interaction.response.edit_message(content="🧛 **제로섬 데스매치를 시작합니다!**", embed=None, view=None)
        await start_zero_round(ctx, cid)

# 제로섬 행동 선택 View
class ZeroSumActionView(discord.ui.View):
    def __init__(self, cid, survivors):
        super().__init__(timeout=40.0)
        self.cid = cid
        self.survivors = survivors
        self.data = zero_games.get(cid)
        
        if len(survivors) == 2:
            # 1대1 상황: 고정 버튼 3개
            btn_atk = discord.ui.Button(label="⚔️ 공격", style=discord.ButtonStyle.danger)
            btn_atk.callback = self.make_dm_callback("attack")
            self.add_item(btn_atk)
            
            btn_def = discord.ui.Button(label="🛡️ 방어", style=discord.ButtonStyle.secondary)
            btn_def.callback = self.make_dm_callback("defense")
            self.add_item(btn_def)
            
            btn_gb = discord.ui.Button(label="🔨 가드 부수기", style=discord.ButtonStyle.primary)
            btn_gb.callback = self.make_dm_callback("guard_break")
            self.add_item(btn_gb)
        else:
            # 다수 대전 상황: 유저별 공격 버튼 + 방어 + 가드 크래시
            for p_id in survivors:
                btn = discord.ui.Button(label=f"⚔️ 공격: {self.data['p_names'][p_id]}", style=discord.ButtonStyle.danger)
                btn.callback = self.make_attack_callback(p_id)
                self.add_item(btn)
            
            def_btn = discord.ui.Button(label="🛡️ 방어", style=discord.ButtonStyle.success)
            def_btn.callback = self.def_btn_callback
            self.add_item(def_btn)

            gb_btn = discord.ui.Button(label="🔨 가드 크래시", style=discord.ButtonStyle.primary)
            gb_btn.callback = self.gb_btn_callback
            self.add_item(gb_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in self.survivors:
            await interaction.response.send_message("💀 현재 생존자만 행동할 수 있습니다!", ephemeral=True)
            return False
        if interaction.user.id in self.data["actions"]:
            await interaction.response.send_message("✅ 이미 행동을 선택하셨습니다. 다른 사람을 기다리세요.", ephemeral=True)
            return False
        return True

    # 1대1 상황용 콜백 팩토리
    def make_dm_callback(self, action_type):
        async def callback(interaction: discord.Interaction):
            self.data["actions"][interaction.user.id] = action_type
            await interaction.response.send_message(f"✅ **[{action_type}]** 선택 완료!", ephemeral=True)
            await self.check_all_voted(interaction)
        return callback

    # 다수 대전용 공격 버튼 콜백 팩토리
    def make_attack_callback(self, target_id):
        async def callback(interaction: discord.Interaction):
            # [🛠️ 상황 B: 자해 방지 로직]
            if int(target_id) == int(interaction.user.id):
                await interaction.response.send_message("❌ 자기 자신은 공격할 수 없습니다!", ephemeral=True)
                return
                
            self.data["actions"][interaction.user.id] = target_id
            await interaction.response.send_message(f"⚔️ **[{self.data['p_names'][target_id]}]** 공격 선택 완료!", ephemeral=True)
            await self.check_all_voted(interaction)
        return callback

    # [🛠️ 수정] 다수 대전용 가드 부수기 콜백
    async def gb_btn_callback(self, interaction: discord.Interaction):
        self.data["actions"][interaction.user.id] = "guard_break"
        await interaction.response.send_message("🔨 **가드 부수기** 준비 완료!", ephemeral=True)
        await self.check_all_voted(interaction)

    # 다수 대전용 방어 버튼 콜백
    async def def_btn_callback(self, interaction: discord.Interaction):
        # [🛠️ 수정] 방어 봉인 디버프 체크
        if interaction.user.id in self.data["debuffs"]:
            await interaction.response.send_message("🚫 **방어 봉인 상태입니다!** 이번 라운드에는 방어할 수 없습니다.", ephemeral=True)
            return
            
        self.data["actions"][interaction.user.id] = "defense"
        await interaction.response.send_message("🛡️ **방어** 태세 선택 완료!", ephemeral=True)
        await self.check_all_voted(interaction)

    async def check_all_voted(self, interaction):
        if len(self.data["actions"]) == len(self.survivors):
            await interaction.message.edit(content="✅ **모든 인원이 행동을 결정했습니다! 결과 공개 중...**", view=None)
            self.stop()

async def start_zero_round(ctx, cid):
    data = zero_games.get(cid)
    if not data: return
    survivors = [p_id for p_id, hp in data["hp"].items() if hp > 0]
    if len(survivors) <= 1:
        winner = data["p_names"][survivors[0]] if survivors else "없음"
        await ctx.send(f"🏆 **데스매치 종료! 최종 승리자: {winner}**")
        if ctx.voice_client: ctx.voice_client.stop()
        del zero_games[cid]; return
    data["actions"] = {}; data["round_survivors"] = survivors
    
    # [🛠️ BGM 복구 및 1대1 브금 전환 트릭]
    is_1v1 = (len(survivors) == 2)
    
    if is_1v1 and not data.get("is_1v1_bgm", False):
        # 다수 대전에서 1대1로 막 넘어온 순간 (BGM 변경 및 재생 시간 초기화)
        data["is_1v1_bgm"] = True
        data["bgm_elapsed"] = 0
        if ctx.voice_client: ctx.voice_client.stop()
        try: await play_sound(ctx, "judgment.mp3")
        except: pass
        data["bgm_start"] = time.time()
        
    elif data["round"] == 1:
        # 1라운드 첫 시작 (처음부터 2명이면 judgment, 3명 이상이면 zero)
        data["is_1v1_bgm"] = is_1v1
        bgm_file = "judgment.mp3" if is_1v1 else "zero.mp3"
        try: await play_sound(ctx, bgm_file)
        except: pass
        data["bgm_start"] = time.time()
        
    else:
        # 일반 라운드 진행 시 (상태에 맞는 BGM 이어듣기)
        if ctx.voice_client:
            if ctx.voice_client.is_playing(): ctx.voice_client.stop()
            filename = "judgment.mp3" if data.get("is_1v1_bgm") else "zero.mp3"
            file_path = os.path.join(BASE_DIR, filename)
            ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg")
            options = f"-vn -ss {data['bgm_elapsed']}"
            if cid not in zero_games: return
            if os.path.exists(file_path):
                try: ctx.voice_client.play(discord.FFmpegPCMAudio(file_path, options=options, executable=ffmpeg_path if os.path.exists(ffmpeg_path) else "ffmpeg"))
                except: pass
            data["bgm_start"] = time.time()
        
    embed = discord.Embed(title=f"🩸 제로섬 - ROUND {data['round']}", color=0xFF0000)
    # HP를 하트 이모지로 표시
    hp_status = "\n".join([f"**{data['p_names'][p_id]}**: {'❤️' * data['hp'][p_id]} ({data['hp'][p_id]})" for p_id in survivors])
    embed.description = f"**현재 생존자 체력:**\n{hp_status}\n\n하단의 버튼을 눌러 행동을 선택하세요!"
    
    view = ZeroSumActionView(cid, survivors)
    await ctx.send(embed=embed, view=view)
    await view.wait()
    await process_zero_result(ctx, cid)

async def process_zero_result(ctx, cid):
    data = zero_games.get(cid)
    if not data: return
    actions = data["actions"]; survivors = data["round_survivors"]; log = []
    changes = {p_id: 0 for p_id in survivors}; attacked_by = {p_id: [] for p_id in survivors}
    
    for pid, act in actions.items():
        if isinstance(act, int): attacked_by[act].append(pid)

    if len(survivors) == 2: # [1대1 데스매치 전용 룰]
        p1, p2 = survivors; a1, a2 = actions.get(p1, "defense"), actions.get(p2, "defense")
        # 1:1 판정 매트릭스
        if a1 == a2:
            if a1 == "defense":
                changes[p1] -= 1; changes[p2] -= 1
                log.append(f"🍃 서로 방어했으나 아무도 공격하지 않아 -1 HP (쫄보)")
            else:
                log.append("⚖️ 서로 같은 태세입니다! 상쇄되었습니다.")
        elif a1 == "attack": # P1 공격
            if a2 == "defense": changes[p1] -= 1; log.append(f"🛡️ {data['p_names'][p2]}의 완벽 방어! {data['p_names'][p1]}님이 역습당했습니다!")
            elif a2 == "guard_break": changes[p1] += 1; changes[p2] -= 1; log.append(f"🔥 가드 부수기를 뚫고 {data['p_names'][p1]}님의 흡혈 성공!")
        elif a1 == "defense": # P1 방어
            if a2 == "attack": changes[p2] -= 1; log.append(f"🛡️ {data['p_names'][p1]}의 완벽 방어! {data['p_names'][p2]}님이 역습당했습니다!")
            elif a2 == "guard_break": changes[p2] -= 2; log.append(f"🔨 {data['p_names'][p2]}님이 방어를 깨부쉈습니다! (방어자 -2 HP)")
        elif a1 == "guard_break": # P1 가드 부수기
            if a2 == "attack": changes[p1] -= 1; changes[p2] += 1; log.append(f"🔥 공격에 당했습니다! {data['p_names'][p2]}님의 흡혈 성공!")
            elif a2 == "defense": changes[p2] -= 2; log.append(f"🔨 {data['p_names'][p1]}님이 방어를 깨부쉈습니다! (방어자 -2 HP)")
            
    else: # [다수 대전 정밀 로직]
        # [🛠️ 수정] 가드 크래시 판정 (공격자 0명, 브레이커 1명 이상, 방어자 1명 이상)
        attackers = [pid for pid in survivors if isinstance(actions.get(pid, "defense"), int)]
        defenders = [pid for pid in survivors if actions.get(pid, "defense") == "defense"]
        breakers = [pid for pid in survivors if actions.get(pid, "defense") == "guard_break"]
        
        if len(attackers) == 0 and len(breakers) >= 1 and len(defenders) >= 1:
            data["debuffs"] = set() # 디버프 초기화 후 시작
            for d_id in defenders:
                changes[d_id] -= 1
                data["debuffs"].add(d_id)
            log.append("🔨 **가드 크래시 성공!** 방어 태세를 취한 유저들의 방패가 박살 났습니다! (방어자 전원 -1 HP & 다음 라운드 방어 불가)")
        else:
            # 가드 크래시 실패 혹은 일반 상황
            data["debuffs"] = set() # 디버프 해제
            for pid in survivors:
                act = actions.get(pid, "defense")
                if act == "defense":
                    if not attacked_by[pid]:
                        changes[pid] -= 1; log.append(f"🍃 {data['p_names'][pid]}님이 방어했으나 아무도 공격하지 않아 -1 HP (쫄보)")
                    else:
                        for atk in attacked_by[pid]:
                            changes[atk] -= 1; log.append(f"🛡️ {data['p_names'][pid]}님이 {data['p_names'][atk]}님의 공격을 반격했습니다! (공격자 -1)")
                elif act == "guard_break":
                    log.append(f"🔨 {data['p_names'][pid]}님은 가드 크래시 실패!")
                elif isinstance(act, int):
                    tgt = act
                    tgt_act = actions.get(tgt, "defense")
                    
                    if tgt_act == pid:
                        # [1] 서로 공격 (상쇄 상태 확정: 절대 피를 빨 수 없음)
                        if pid < tgt:   # 로그만 한 번 출력하도록 제어
                            log.append(f"⚔️ {data['p_names'][pid]} ↔️ {data['p_names'][tgt]} 공격 기운이 상쇄되었습니다!")
                    else:
                        # [2] 서로 공격한 게 아닐 때만 흡혈 판정 진입
                        if tgt_act != "defense":
                            # 상대가 방어가 아니면 무조건 흡혈 성공
                            changes[pid] += 1
                            changes[tgt] -= 1
                            log.append(f"🩸 {data['p_names'][pid]}님이 {data['p_names'][tgt]}님의 피를 빨았습니다! (+1 HP / -1 HP)")
    for pid, diff in changes.items():
        data["hp"][pid] += diff
        if data["hp"][pid] <= 0: log.append(f"💀 **{data['p_names'][pid]} 탈락!**")
    
    # [🛠️ BGM 이어 듣기 및 효과음 구현]
    data["bgm_elapsed"] += time.time() - data["bgm_start"]
    if ctx.voice_client:
        ctx.voice_client.stop()
        try: ctx.voice_client.play(discord.FFmpegPCMAudio("sword.mp3"))
        except: pass
    await ctx.send(embed=discord.Embed(title=f"📊 라운드 {data['round']} 결과", description="\n".join(log), color=0xFFFF00))
    data["round"] += 1
    class NextView(discord.ui.View):
        @discord.ui.button(label="➡️ 다음 라운드 진행", style=discord.ButtonStyle.success)
        async def next(self, interaction: discord.Interaction, btn: discord.ui.Button):
            # [🛠️ 수정 1] 상호작용 실패 방지
            await interaction.response.edit_message(view=None)
            await start_zero_round(ctx, cid)
    await ctx.send("준비되셨나요?", view=NextView(timeout=None))

@bot.command(name="제로섬")
async def cmd_zerosum(ctx):
    if ctx.channel.id in zero_games:
        await ctx.send("이미 게임이 진행 중입니다."); return
    if not ctx.author.voice:
        await ctx.send("먼저 음성 채널에 접속해 주세요!"); return
    if ctx.voice_client is None: await ctx.author.voice.channel.connect()
    elif ctx.voice_client.channel != ctx.author.voice.channel: await ctx.voice_client.move_to(ctx.author.voice.channel)
    try: await play_sound(ctx, "intro.mp3")
    except: pass
    await ctx.send(embed=discord.Embed(title="🩸 제로섬 데스매치 모집", description="HP 5로 시작하는 흡혈귀 게임!\n\n참가하려면 **[참여하기]** 클릭", color=0xFF0000), view=ZeroJoinView(ctx.author))


# 👇 토큰
# bot.run은 모든 명령어 정의 후 파일 맨 하단에서 실행됩니다.

# ==========================================
# 🦁 팀전 양세찬 게임 (Team Yang Se-chan Game)
# ==========================================
yang_se_chan_games = {}

# [🛠️ 양세찬 전용 오디오 유틸]
SECHAN_BGM_DIR = os.path.join(BASE_DIR, "sechan_bgm")

async def play_sechan_bgm(ctx_or_int, filename, resume=False):
    # 1. Interaction인지 Context인지 구분하여 안전하게 정보 추출
    if hasattr(ctx_or_int, "response"): # Interaction 객체
        author = ctx_or_int.user
        guild = ctx_or_int.guild
        cid = ctx_or_int.channel_id
    else: # Context 객체
        author = ctx_or_int.author
        guild = ctx_or_int.guild
        cid = ctx_or_int.channel.id

    # 모집/세팅 단계에서는 data가 없어도 intro, sechan1 재생을 허용함
    data = yang_se_chan_games.get(cid, {}) 
    
    ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg")
    file_path = os.path.join(SECHAN_BGM_DIR, filename)
    if not os.path.exists(file_path): return
    
    vc = guild.voice_client
    if vc is not None:
        pass # 봇이 이미 음성방에 있다면 그대로 사용
    else:
        # 봇이 음성방에 없을 때만 유저의 채널을 찾아서 들어감
        if not getattr(author, 'voice', None): return
        channel = author.voice.channel
        vc = await channel.connect()
        
    if vc.is_playing(): vc.stop()
    
    options = ""
    if resume and filename == "sechan2.mp3":
        elapsed = data.get("bgm_elapsed_time", 0)
        options = f"-vn -ss {elapsed}"
        
    try:
        vc.play(discord.FFmpegPCMAudio(file_path, options=options, executable=ffmpeg_path if os.path.exists(ffmpeg_path) else "ffmpeg"))
        if filename == "sechan2.mp3" and cid in yang_se_chan_games:
            yang_se_chan_games[cid]["bgm_start_time"] = time.time()
    except Exception as e:
        print(f"BGM 재생 오류: {e}")

async def play_sechan_sfx(ctx, sfx_filename, sleep_time=2.5):
    cid = ctx.channel.id
    if cid not in yang_se_chan_games: return
    data = yang_se_chan_games[cid]

    # 1. 기존 브금 진행 시간 저장
    if "bgm_start_time" in data:
        current_elapsed = time.time() - data["bgm_start_time"]
        data["bgm_elapsed_time"] = data.get("bgm_elapsed_time", 0) + current_elapsed
        del data["bgm_start_time"]

    # 2. 효과음 재생
    await play_sechan_bgm(ctx, sfx_filename)

    # 3. 효과음 재생 시간만큼 대기
    await asyncio.sleep(sleep_time)

    # 4. 메인 브금 다시 이어듣기
    await play_sechan_bgm(ctx, "sechan2.mp3", resume=True)

# [🛠️ 양세찬 유틸: Modal 및 View]
class WordInputModal(discord.ui.Modal):
    def __init__(self, team_key, team_name, cid):
        super().__init__(title=f"📝 {team_name} 제시어 입력")
        self.team_key = team_key
        self.cid = cid
        self.word_input = discord.ui.TextInput(
            label="상대 팀이 맞힐 단어",
            placeholder="예: 사과, 아이언맨, 독서 등",
            min_length=1,
            max_length=20
        )
        self.add_item(self.word_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True) # 생각할 시간 벌기 (3초 타임아웃 방지)
        
        data = yang_se_chan_games.get(self.cid)
        if not data: return
        
        word = self.word_input.value
        data[self.team_key]["word"] = word
        
        # DM 전송 (사회자와 해당 팀원들)
        target_team = data[self.team_key]
        mod = data["moderator"]
        try: await mod.send(f"📢 [{target_team['name']}]이 정한 단어 (상대 팀 제시어): **{word}**")
        except: pass
        for p in target_team["players"]:
            try: await p.send(f"📢 우리 팀이 정한 단어 (상대 팀 제시어): **{word}**")
            except: pass
            
        await interaction.followup.send(f"✅ **{target_team['name']}** 제시어 설정 완료!", ephemeral=True)
        
        # 양쪽 다 설정되면 시작
        if data["team1"]["word"] and data["team2"]["word"]:
            ctx = await bot.get_context(interaction.message)
            ctx.author = interaction.user # 음성 채널 인식을 위해 필수
            await start_yang_se_chan_loop(ctx, self.cid)

class WordSetupView(discord.ui.View):
    def __init__(self, cid):
        super().__init__(timeout=None)
        self.cid = cid
        data = yang_se_chan_games.get(cid)
        
        btn1 = discord.ui.Button(label=f"📝 {data['team1']['name']} 제시어 입력", style=discord.ButtonStyle.primary)
        btn1.callback = self.make_callback("team1")
        self.add_item(btn1)
        
        btn2 = discord.ui.Button(label=f"📝 {data['team2']['name']} 제시어 입력", style=discord.ButtonStyle.primary)
        btn2.callback = self.make_callback("team2")
        self.add_item(btn2)

    def make_callback(self, team_key):
        async def callback(interaction: discord.Interaction):
            data = yang_se_chan_games.get(self.cid)
            if not data: return
            
            # 해당 팀의 1번 타자인지 확인
            team_data = data[team_key]
            if interaction.user.id != team_data["players"][0].id:
                await interaction.response.send_message("❌ 각 팀의 **1번 타자**만 입력할 수 있습니다!", ephemeral=True)
                return
            
            if team_data["word"]:
                await interaction.response.send_message("이미 제시어를 입력했습니다!", ephemeral=True)
                return
                
            await interaction.response.send_modal(WordInputModal(team_key, team_data["name"], self.cid))
        return callback

class YangSeChanJoinView(discord.ui.View):
    def __init__(self, host, moderator_target=None):
        super().__init__(timeout=60.0)
        self.host = host
        self.moderator = moderator_target # 지정된 사회자 (없으면 나중에 랜덤)
        self.players = [host]
        self.team1_players = []
        self.team2_players = []
        self.team1_name = "사자팀"
        self.team2_name = "호랑이팀"
        
        # 주제/동물.txt에서 팀 이름 가져오기
        try:
            with open(os.path.join(BASE_DIR, "주제", "동물.txt"), "r", encoding="utf-8") as f:
                animals = [l.strip() for l in f if l.strip()]
                if len(animals) >= 2:
                    names = random.sample(animals, 2)
                    self.team1_name = f"{names[0]}팀"
                    self.team2_name = f"{names[1]}팀"
        except: pass
        
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        btn_join = discord.ui.Button(label="🙋‍♂️ 참여하기", style=discord.ButtonStyle.green)
        btn_join.callback = self.join_callback
        self.add_item(btn_join)
        
        btn_t1 = discord.ui.Button(label=f"🚩 {self.team1_name}", style=discord.ButtonStyle.secondary)
        btn_t1.callback = self.make_team_callback(1)
        self.add_item(btn_t1)
        
        btn_t2 = discord.ui.Button(label=f"🚩 {self.team2_name}", style=discord.ButtonStyle.secondary)
        btn_t2.callback = self.make_team_callback(2)
        self.add_item(btn_t2)
        
        btn_start = discord.ui.Button(label="🚀 게임시작", style=discord.ButtonStyle.primary)
        btn_start.callback = self.start_callback
        self.add_item(btn_start)

    async def join_callback(self, interaction: discord.Interaction):
        if interaction.user in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        await self.refresh_msg(interaction)

    def make_team_callback(self, team_num):
        async def callback(interaction: discord.Interaction):
            if interaction.user not in self.players:
                await interaction.response.send_message("먼저 '참여하기'를 눌러주세요!", ephemeral=True)
                return
            
            # 기존 팀에서 제거
            if interaction.user in self.team1_players: self.team1_players.remove(interaction.user)
            if interaction.user in self.team2_players: self.team2_players.remove(interaction.user)
            
            if team_num == 1: self.team1_players.append(interaction.user)
            else: self.team2_players.append(interaction.user)
            
            await self.refresh_msg(interaction)
        return callback

    async def start_callback(self, interaction: discord.Interaction):
        if interaction.user != self.host:
            await interaction.response.send_message("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if not self.team1_players or not self.team2_players:
            await interaction.response.send_message("양쪽 팀에 최소 1명씩은 있어야 합니다!", ephemeral=True)
            return
        
        cid = interaction.channel.id
        # 사회자 확정
        if self.moderator and self.moderator not in self.players:
            # 지정 사회자가 참여 안했으면 참가자 중 랜덤
            mod = random.choice(self.players)
        elif self.moderator:
            mod = self.moderator
        else:
            mod = random.choice(self.players)
            
        # 사회자는 플레이어에서 제외 (심판 역할)
        participants = [p for p in self.players if p.id != mod.id]
        t1 = [p for p in self.team1_players if p.id != mod.id]
        t2 = [p for p in self.team2_players if p.id != mod.id]
        
        if not t1 or not t2:
             await interaction.response.send_message("사회자를 제외한 팀원이 각 팀에 최소 1명 필요합니다!", ephemeral=True)
             return

        yang_se_chan_games[cid] = {
            "status": "setting",
            "moderator": mod,
            "team1": {"name": self.team1_name, "players": t1, "word": "", "order": []},
            "team2": {"name": self.team2_name, "players": t2, "word": "", "order": []},
            "team1_lives": 5,
            "team2_lives": 5,
            "warnings": {}, # user_id: count
            "turn_team": None, # 1 or 2
            "team1_member_idx": 0,
            "team2_member_idx": 0,
            "eliminated": set(),
            "bgm_start_time": 0,
            "bgm_elapsed_time": 0
        }
        
        embed = discord.Embed(title="🦁 양세찬 게임 세팅 시작!", color=0x3498DB)
        embed.description = f"**사회자:** {mod.mention}\n\n" \
                            f"**{self.team1_name}:** {' '.join([p.mention for p in t1])}\n" \
                            f"**{self.team2_name}:** {' '.join([p.mention for p in t2])}\n\n" \
                            f"각 팀의 **1번 타자**({t1[0].mention}, {t2[0].mention})는\n" \
                            f"아래 버튼을 눌러 제시어를 팝업창에 입력해 주세요!"
        
        await interaction.response.edit_message(embed=embed, view=WordSetupView(cid))
        
        # [🔊 BGM 전환: sechan1.mp3]
        await play_sechan_bgm(interaction, "sechan1.mp3")

    async def refresh_msg(self, interaction):
        embed = interaction.message.embeds[0]
        
        selected_ids = [p.id for p in self.team1_players + self.team2_players]
        waiting_list = [p.mention for p in self.players if p.id not in selected_ids]
        selected_list = [p.mention for p in self.players if p.id in selected_ids]
        
        waiting_text = ', '.join(waiting_list) if waiting_list else "없음"
        selected_text = ', '.join(selected_list) if selected_list else "없음"
        
        embed.description = f"⏳ **대기 인원:** {waiting_text} (팀을 선택해주세요!)\n" \
                            f"✅ **선택 완료:** {selected_text}\n\n" \
                            f"🤫 **현재 팀 선택은 철저히 비공개입니다!**\n" \
                            f"팀 선택 버튼을 눌러 팀을 확정하세요. (누가 어느 팀인지는 게임이 시작되어야 공개됩니다.)"
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command(name="양세찬")
async def cmd_yang_se_chan(ctx, target: discord.Member = None):
    # [🔊 BGM 시작: intro.mp3]
    await play_sechan_bgm(ctx, "intro.mp3")

    if target is None:
        await ctx.send(f"❌ **사회자를 반드시 지정해야 합니다!**\n사용법: `{PREFIX}양세찬 @유저` (지정된 유저는 심판 역할을 맡습니다.)")
        return
        
    if ctx.channel.id in yang_se_chan_games:
        await ctx.send("❌ 이미 진행 중인 양세찬 게임이 있습니다.")
        return
    view = YangSeChanJoinView(ctx.author, target)
    embed = discord.Embed(title="🦁 팀전 양세찬 게임 모집", 
                          description=f"⏳ **대기 인원:** {ctx.author.mention} (팀을 선택해주세요!)\n"
                                      f"✅ **선택 완료:** 없음\n\n"
                                      f"🤫 **현재 팀 선택은 철저히 비공개입니다!**\n"
                                      f"팀 선택 버튼을 눌러 팀을 확정하세요. (누가 어느 팀인지는 게임이 시작되어야 공개됩니다.)", 
                          color=0xFFA500)
    await ctx.send(embed=embed, view=view)

# !제시어 명령어는 이제 Modal 방식을 사용하므로 삭제되었습니다.

async def start_yang_se_chan_loop(ctx, cid):
    # [🔊 BGM 전환: sechan2.mp3 (팝업창 닫힘 딜레이 고려)]
    await asyncio.sleep(1)
    await play_sechan_bgm(ctx, "sechan2.mp3")
    
    data = yang_se_chan_games[cid]
    data["status"] = "playing"
    data["is_first_turn"] = True # 첫 턴 표시
    
    # 기록 시스템 세분화 (질문/대답 분리)
    data["team1"]["questions"] = []
    data["team1"]["answers"] = []
    data["team2"]["questions"] = []
    data["team2"]["answers"] = []
    
    # 순서 섞기
    data["team1"]["order"] = random.sample(data["team1"]["players"], len(data["team1"]["players"]))
    data["team2"]["order"] = random.sample(data["team2"]["players"], len(data["team2"]["players"]))
    
    # 선공 결정
    data["turn_team"] = random.choice([1, 2])
    data["team1_member_idx"] = 0
    data["team2_member_idx"] = 0
    
    embed = discord.Embed(title="🎮 양세찬 게임 시작!", color=0x2ECC71)
    t1 = data["team1"]
    t2 = data["team2"]
    start_team_name = t1["name"] if data["turn_team"] == 1 else t2["name"]
    
    embed.add_field(name=f"🚩 {t1['name']}", value=" -> ".join([p.name for p in t1["order"]]), inline=False)
    embed.add_field(name=f"🚩 {t2['name']}", value=" -> ".join([p.name for p in t2["order"]]), inline=False)
    embed.description = f"🎲 선공 팀: **{start_team_name}**\n\n지금부터 질문을 주고받으세요!\n자신의 턴에는 질문을 하고, 상대 팀은 답변해 줍니다.\n`{PREFIX}정답 [단어]` 명령어로 언제든 도전 가능! (팀 공유 목숨 5개)"
    
    await ctx.send(embed=embed)
    
    await announce_turn(ctx, cid)

async def announce_turn(ctx, cid):
    data = yang_se_chan_games.get(cid)
    if not data: return
    
    team_data = data[f"team{data['turn_team']}"]
    # 생존자 필터링
    alive_order = [p for p in team_data["order"] if p.id not in data["eliminated"]]
    
    if not alive_order:
        # 팀 전원 탈락 시 패배
        await end_yang_se_chan(ctx, cid, 3 - data["turn_team"])
        return
        
    t_idx_key = f"team{data['turn_team']}_member_idx"
    current_p = alive_order[data[t_idx_key] % len(alive_order)]
    
    # 순서 시각화
    order_display = ""
    for p in team_data["order"]:
        if p.id in data["eliminated"]:
            order_display += f"~~{p.name}~~(💀) "
        elif p.id == current_p.id:
            order_display += f"▶️ **{p.name}** "
        else:
            order_display += f"{p.name} "
    
    # [핵심] 채팅 감지 및 자동 턴 넘김 로직
    current_turn_idx = data[t_idx_key]
    cid = ctx.channel.id
    if cid not in yang_se_chan_games: return
    
    def check(m):
        # 현재 차례인 유저가 친 일반 대화(명령어 아님)만 감지
        return m.channel.id == cid and m.author.id == current_p.id and not m.content.startswith(PREFIX)

    try:
        if data.get("is_first_turn", False):
            # [첫 턴: 질문만 던짐]
            embed = discord.Embed(title=f"🔔 {team_data['name']} 차례 (첫 질문)", color=0xF1C40F)
            embed.description = f"**순서:** {order_display}\n" \
                                f"❤️ {data['team1']['name']}: {data['team1_lives']}/5 | 💙 {data['team2']['name']}: {data['team2_lives']}/5\n\n" \
                                f"👉 {current_p.mention}님, 상대 팀이 맞히기 어려운 첫 **질문**을 던져주세요!"
            if cid not in yang_se_chan_games: return
            await ctx.send(embed=embed)
            msg = await bot.wait_for('message', timeout=300.0, check=check)
            data[f"team{data['turn_team']}"]["questions"].append(msg.content)
            await msg.add_reaction("✅")
            data["is_first_turn"] = False
        else:
            # [일반 턴: 대답 후 질문]
            # Step 1. 대답하기
            embed_ans = discord.Embed(title=f"🔔 {team_data['name']} 차례", color=0xF1C40F)
            if cid not in yang_se_chan_games: return
            embed_ans.description = f"**순서:** {order_display}\n" \
                                    f"❤️ {data['team1']['name']}: {data['team1_lives']}/5 | 💙 {data['team2']['name']}: {data['team2_lives']}/5"
            embed_ans.add_field(name="Step 1. 대답하기", value=f"👉 {current_p.mention}님, 먼저 상대 팀의 질문에 솔직하게 **대답**해 주세요!", inline=False)
            await ctx.send(embed=embed_ans)
            
            msg_ans = await bot.wait_for('message', timeout=300.0, check=check)
            data[f"team{data['turn_team']}"]["answers"].append(msg_ans.content)
            await msg_ans.add_reaction("✅")
            await asyncio.sleep(0.5)

            # Step 2. 질문하기
            embed_que = discord.Embed(title=f"🔔 {team_data['name']} 차례", color=0xF1C40F)
            embed_que.description = f"**순서:** {order_display}\n" \
                                    f"❤️ {data['team1']['name']}: {data['team1_lives']}/5 | 💙 {data['team2']['name']}: {data['team2_lives']}/5"
            embed_que.add_field(name="Step 2. 질문하기", value="좋습니다! 이제 상대 팀에게 추리용 **질문**을 던져주세요!", inline=False)
            await ctx.send(embed=embed_que)
            
            msg_que = await bot.wait_for('message', timeout=300.0, check=check)
            data[f"team{data['turn_team']}"]["questions"].append(msg_que.content)
            await msg_que.add_reaction("✅")

        # 그 사이 사회자가 강제로 턴을 넘기지 않았다면 정상적으로 다음 턴 진행
        if cid in yang_se_chan_games and data[t_idx_key] == current_turn_idx:
            await check_and_next_turn(ctx, cid)
    except asyncio.TimeoutError:
        pass

@bot.command(name="정보")
async def cmd_yang_info(ctx):
    cid = ctx.channel.id
    if cid not in yang_se_chan_games: return
    data = yang_se_chan_games[cid]
    if data["status"] != "playing": return
    
    # 어느 팀인지 확인
    my_team_num = 1 if any(p.id == ctx.author.id for p in data["team1"]["players"]) else 2
    opp_team_num = 3 - my_team_num
    
    my_team = data[f"team{my_team_num}"]
    opp_team = data[f"team{opp_team_num}"]
    
    questions = my_team.get("questions", [])
    answers = opp_team.get("answers", []) # 상대가 우리 질문에 답한 기록
    
    if not questions:
        await ctx.send(f"📊 **[{my_team['name']}]** 아직 기록된 질문이 없습니다.", delete_after=10)
        return
        
    embed = discord.Embed(title=f"📊 {my_team['name']} 기록실 (우리 질문 ➡️ 상대 대답)", color=0x3498DB)
    content = ""
    for i in range(len(questions)):
        q = questions[i]
        a = answers[i] if i < len(answers) else "*(대기 중...)*"
        content += f"**{i+1}. Q:** {q}\n   **┕ A:** {a}\n\n"
    
    embed.description = content
    embed.set_footer(text="이 메시지는 20초 후 자동으로 사라집니다.")
    
    await ctx.send(embed=embed, delete_after=20)
    try: await ctx.message.delete()
    except: pass

@bot.command(name="정답")
async def cmd_yang_answer(ctx, word: str):
    cid = ctx.channel.id
    if cid not in yang_se_chan_games: return
    data = yang_se_chan_games[cid]
    if data["status"] != "playing": return
    if ctx.author.id in data["eliminated"]: return
    
    # 어느 팀인지 확인
    user_team_num = 0
    if cid not in yang_se_chan_games: return
    if any(p.id == ctx.author.id for p in data["team1"]["players"]): user_team_num = 1
    elif any(p.id == ctx.author.id for p in data["team2"]["players"]): user_team_num = 2
    else: return # 사회자 등은 정답 불가
    
    # 내가 맞히려는 단어는 '상대 팀'이 설정한 것
    target_team_num = 3 - user_team_num
    correct_word = data[f"team{target_team_num}"]["word"].replace(" ", "")
    input_word = word.replace(" ", "")
    
    if input_word == correct_word:
        # [🔊 정답: carry.mp3 재생 후 대기]
        await play_sechan_bgm(ctx, "carry.mp3")
        await ctx.send("🎉 **정답입니다!!**\n축하 음악이 끝난 후 게임이 종료됩니다.")
        
        # BGM이 끝날 때까지 안전하게 대기
        vc = ctx.guild.voice_client
        if vc:
            while vc.is_playing():
                await asyncio.sleep(1)
        
        await end_yang_se_chan(ctx, cid, user_team_num)
    else:
        data[f"team{user_team_num}_lives"] -= 1
        rem = data[f"team{user_team_num}_lives"]
        
        if rem <= 0:
            await ctx.send(f"❌ 틀렸습니다! **{data[f'team{user_team_num}']['name']}**이 모든 목숨을 잃어 패배했습니다!")
            await end_yang_se_chan(ctx, cid, 3 - user_team_num)
        else:
            await play_sechan_sfx(ctx, "down.mp3", sleep_time=3.0) # 오답 시 down.mp3
            await ctx.send(f"❌ 틀렸습니다! **{data[f'team{user_team_num}']['name']}** 팀 목숨 1개 감소 (남은 팀 목숨: {rem}/5)")

async def check_and_next_turn(ctx, cid, eliminated_id=None):
    data = yang_se_chan_games.get(cid)
    if not data: return
    
    # 해당 팀의 인덱스만 증가
    data[f"team{data['turn_team']}_member_idx"] += 1
    # 턴 교체
    data["turn_team"] = 3 - data["turn_team"]
    await announce_turn(ctx, cid)

@bot.command(name="다음턴")
async def cmd_next_turn_manual(ctx):
    cid = ctx.channel.id
    if cid not in yang_se_chan_games: return
    data = yang_se_chan_games[cid]
    if ctx.author.id != data["moderator"].id: return # 사회자만 가능
    
    # 해당 팀의 인덱스만 증가
    data[f"team{data['turn_team']}_member_idx"] += 1
    # 턴 교체
    data["turn_team"] = 3 - data["turn_team"]
    await announce_turn(ctx, cid)

# --- 사회자 심판 시스템 ---
@bot.command(name="옐로카드")
async def cmd_yellow(ctx, target: discord.Member):
    cid = ctx.channel.id
    if cid not in yang_se_chan_games: return
    data = yang_se_chan_games[cid]
    if ctx.author.id != data["moderator"].id: return
    
    count = data["warnings"].get(target.id, 0) + 1
    data["warnings"][target.id] = count
    
    await play_sechan_sfx(ctx, "card.mp3", sleep_time=2.0) # 옐로카드 효과음 (2초 대기 후 resume)
    
    if count >= 2:
        await ctx.send(f"🟨 **옐로카드 누적!** {target.mention}님은 경고 2회로 레드카드를 받습니다.")
        await cmd_red(ctx, target)
    else:
        await ctx.send(f"🟨 **옐로카드!** {target.mention}님 경고 1회 부여. (누적 2장 시 퇴장)")

@bot.command(name="레드카드")
async def cmd_red(ctx, target: discord.Member):
    cid = ctx.channel.id
    if cid not in yang_se_chan_games: return
    data = yang_se_chan_games[cid]
    if ctx.author.id != data["moderator"].id: return
    
    # 현재 질문 차례의 유저 계산 (탈락 처리 전 기준)
    turn_team_num = data["turn_team"]
    team_data_current = data[f"team{turn_team_num}"]
    # 아직 이 로직은 탈락자 명단(target)을 포함하고 있는지 여부에 주의해야 함. 
    # 현재 alive_order를 구해서 current_p를 찾음
    alive_order = [p for p in team_data_current["order"] if p.id not in data["eliminated"]]
    current_p = None
    if alive_order:
        t_idx_key = f"team{turn_team_num}_member_idx"
        current_p = alive_order[data[t_idx_key] % len(alive_order)]
    
    # 이제 탈락 처리 (위에서 current_p를 구했으므로)
    data["eliminated"].add(target.id)
    await play_sechan_sfx(ctx, "card.mp3", sleep_time=2.0) # 레드카드 효과음
    await ctx.send(f"🟥 **레드카드!!** {target.mention}님은 즉시 게임에서 탈락(퇴장) 처리되었습니다.")

    # 레드카드 받은 사람의 소속 팀 찾기
    target_team_num = 1 if any(p.id == target.id for p in data["team1"]["players"]) else 2
    team_data_target = data[f"team{target_team_num}"]

    # 팀 전원 탈락 여부 체크 (남은 생존자가 있는지)
    alive_players = [p for p in team_data_target["players"] if p.id not in data["eliminated"]]
    if not alive_players:
        await ctx.send(f"📢 **{team_data_target['name']}**의 모든 팀원이 퇴장당해 몰수패 당했습니다!")
        await end_yang_se_chan(ctx, cid, 3 - target_team_num) # 상대 팀 승리 처리
        return

    # 턴 판정
    if current_p and target.id == current_p.id:
        await ctx.send("📢 현재 질문자가 탈락했으므로 상대 팀으로 턴을 넘깁니다.")
        await check_and_next_turn(ctx, cid)
    else:
        await ctx.send("📢 질문자가 아니므로 현재 턴은 그대로 유지됩니다.")

@bot.command(name="정답인정")
async def cmd_judge_correct(ctx, target: discord.Member):
    cid = ctx.channel.id
    if cid not in yang_se_chan_games: return
    data = yang_se_chan_games[cid]
    if ctx.author.id != data["moderator"].id: return
    
    # 어느 팀인지 확인
    win_team_num = 0
    if any(p.id == target.id for p in data["team1"]["players"]): win_team_num = 1
    elif any(p.id == target.id for p in data["team2"]["players"]): win_team_num = 2
    
    if win_team_num > 0:
        await ctx.send(f"⚖️ **사회자 판정!** {target.name}님의 답변을 정답으로 인정합니다.")
        await end_yang_se_chan(ctx, cid, win_team_num)

async def end_yang_se_chan(ctx, cid, winner_team_num):
    data = yang_se_chan_games.get(cid)
    if not data: return
    
    win_team = data[f"team{winner_team_num}"]
    lose_team = data[f"team{3-winner_team_num}"]
    
    embed = discord.Embed(title="🏁 양세찬 게임 종료!", color=0xFFD700)
    embed.description = f"🏆 승리: **{win_team['name']}**\n💀 패배: {lose_team['name']}\n\n" \
                        f"**[{win_team['name']}] 정답:** {lose_team['word']}\n" \
                        f"**[{lose_team['name']}] 정답:** {win_team['word']}"
    
    await ctx.send(embed=embed)
    
    # [🔊 오디오 정리]
    if ctx.voice_client: ctx.voice_client.stop()
    
    del yang_se_chan_games[cid]

@bot.command(name="양세찬종료")
async def cmd_stop_yang(ctx):
    cid = ctx.channel.id
    if cid in yang_se_chan_games:
        del yang_se_chan_games[cid]
        if ctx.voice_client: ctx.voice_client.stop()
        await ctx.send("🛑 양세찬 게임을 강제 종료했습니다.")
    else: await ctx.send("❌ 진행 중인 양세찬 게임이 없습니다.")

# ==========================================
# 🧟 좀비 런 (Zombie Run)
# ==========================================
zombie_games = {}

class ZombieJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=60.0)
        self.host = host
        self.players = [host]

    @discord.ui.button(label="🙋‍♂️ 참여하기", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        if len(self.players) >= 7:
            await interaction.response.send_message("최대 7명까지만 참여 가능합니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        embed.description = f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n(최소 2명 ~ 최대 7명 필요)"
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🚀 게임시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 2:
            await interaction.response.send_message("최소 2명 이상의 참가자가 필요합니다!", ephemeral=True)
            return

        cid = interaction.channel.id
        if cid in zombie_games:
            await interaction.response.send_message("이미 진행 중인 게임이 있습니다.", ephemeral=True)
            return
            
        pcnt = len(self.players)
        if pcnt <= 4: btns = [1, 3, 5]
        elif pcnt == 5: btns = [2, 3, 5, 6]
        elif pcnt == 6: btns = [2, 3, 4, 5, 6]
        elif pcnt == 7: btns = [1, 2, 3, 4, 5, 6]
        else: btns = [1, 2, 3, 4, 5]

        zombie_games[cid] = {
            "status": "playing",
            "players": self.players,
            "zombie_pos": {p.id: 0 for p in self.players},
            "survivor_pos": {p.id: 0 for p in self.players},
            "is_zombie": {p.id: False for p in self.players},
            "zombie_order": [],
            "ai_zombie_pos": 0,
            "starvation": 0,
            "buttons": btns,
            "round": 1
        }

        await interaction.message.edit(content="🚀 **좀비런 게임을 시작합니다!**", embed=None, view=None)
        self.stop()
        
        ctx = await bot.get_context(interaction.message)
        ctx.author = interaction.user
        bot.loop.create_task(start_zombie_game(ctx, cid))

@bot.command(name="좀비런")
async def cmd_zombie_run(ctx):
    if ctx.channel.id in zombie_games:
        await ctx.send("❌ 이미 진행 중인 좀비런 게임이 있습니다.")
        return
    if not ctx.author.voice:
        await ctx.send("❌ 먼저 음성 채널에 접속해 주세요!")
        return
    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()
    elif ctx.voice_client.channel != ctx.author.voice.channel:
        await ctx.voice_client.move_to(ctx.author.voice.channel)
        
    try: await play_sound(ctx, "intro.mp3")
    except: pass
        
    embed = discord.Embed(title="🧟 좀비런 모집", description=f"**현재 참가자:** {ctx.author.mention}\n(최소 2명 ~ 최대 7명 필요)", color=0x8B0000)
    view = ZombieJoinView(ctx.author)
    await ctx.send(embed=embed, view=view)

@bot.command(name="좀비런종료")
async def cmd_stop_zombie(ctx):
    cid = ctx.channel.id
    if cid in zombie_games:
        del zombie_games[cid]
        if ctx.voice_client and ctx.voice_client.is_playing(): ctx.voice_client.stop()
        await ctx.send("🛑 좀비런 게임을 강제 종료했습니다.")
    else:
        await ctx.send("❌ 진행 중인 좀비런 게임이 없습니다.")

class ZombieMoveView(discord.ui.View):
    def __init__(self, buttons, survivors):
        super().__init__(timeout=30.0)
        self.choices = {}
        self.survivors = survivors
        self.finished = False

        for b in buttons:
            btn = discord.ui.Button(label=str(b), style=discord.ButtonStyle.blurple, custom_id=f"zb_{b}")
            btn.callback = self.make_callback(b)
            self.add_item(btn)

    def make_callback(self, val):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id not in [s.id for s in self.survivors]:
                await interaction.response.send_message("귀하는 현재 이동 가능한 생존자가 아닙니다!", ephemeral=True)
                return
            if interaction.user.id in self.choices:
                await interaction.response.send_message("이미 선택했습니다!", ephemeral=True)
                return
            
            self.choices[interaction.user.id] = val
            await interaction.response.send_message(f"[{val}] 칸 전진을 선택하셨습니다.", ephemeral=True)

            if len(self.choices) == len(self.survivors):
                self.finished = True
                self.stop()
        return cb

class ZombieRollView(discord.ui.View):
    def __init__(self, zombie_id, label="주사위 굴리기 🎲"):
        super().__init__(timeout=30.0)
        self.zombie_id = zombie_id
        self.rolled = False

        btn = discord.ui.Button(label=label, style=discord.ButtonStyle.danger, custom_id="zb_roll")
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != self.zombie_id:
                await interaction.response.send_message("당신의 턴이 아닙니다!", ephemeral=True)
                return
            self.rolled = True
            await interaction.response.defer()
            self.stop()
        btn.callback = cb
        self.add_item(btn)

async def start_zombie_game(ctx, cid):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
    try: await play_sound(ctx, "run.mp3")
    except: pass
    
    data = zombie_games.get(cid)
    if not data: return
    
    data["bgm_start_time"] = time.time()
    data["bgm_elapsed"] = 0
    
    while cid in zombie_games:
        data["round_new_infections"] = 0
        r = data["round"]
        
        embed = discord.Embed(title=f"🧟 ROUND {r} 시작!", color=0x3498DB)
        survivor_names = [p.name for p in data["players"] if not data["is_zombie"][p.id]]
        zombie_count = sum(1 for p in data["players"] if data["is_zombie"][p.id])
        
        embed.add_field(name="✨ 남은 생존자", value=", ".join(survivor_names) if survivor_names else "없음", inline=False)
        embed.add_field(name="🩸 현재 상태", value=f"아사 스택: {data['starvation']}/3 | 플레이어 좀비: {zombie_count}명", inline=False)
        await ctx.send(embed=embed)

        await asyncio.sleep(2)
        if cid not in zombie_games: return
        
        # 3 이동 페이즈
        for turn in range(1, 4):
            if cid not in zombie_games: return
            survivors = [p for p in data["players"] if not data["is_zombie"][p.id]]
            if not survivors:
                break
                
            current_btns = data["buttons"]
            view = ZombieMoveView(current_btns, survivors)
            msg = await ctx.send(f"🏃 **[ROUND {r} - 턴 {turn}/3]** 생존자들은 전진할 칸수를 선택하세요! (30초)", view=view)
            
            await view.wait()
            if cid not in zombie_games: return
            await msg.edit(view=None)
            
            choices = view.choices
            counts = {}
            for v in choices.values():
                counts[v] = counts.get(v, 0) + 1
            
            result_str = f"🏁 **[턴 {turn} 결과]**\n"
            for p in survivors:
                val = choices.get(p.id, 0)
                if val == 0:
                    result_str += f"- {p.name}: 미선택 (0칸)\n"
                elif counts[val] >= 2:
                    result_str += f"- {p.name}: [{val}] 선택 💥 (발 꼬임! 0칸)\n"
                else:
                    data["survivor_pos"][p.id] += val
                    result_str += f"- {p.name}: [{val}] 선택 💨 (+{val}칸)\n"
                    
            await ctx.send(result_str)
            await asyncio.sleep(1.5)
            if cid not in zombie_games: return
            
            pos_str = "📍 **현재 생존자 위치**\n"
            for p in survivors:
                pos_str += f"{p.name}: {data['survivor_pos'][p.id]}칸\n"
            await ctx.send(pos_str)
            await asyncio.sleep(2)
            if cid not in zombie_games: return

        survivors = [p for p in data["players"] if not data["is_zombie"][p.id]]
        if len(survivors) == 1:
            winner = survivors[0]
            embed = discord.Embed(
                title="🏆 ZOMBIE RUN FINAL SURVIVOR",
                description=f"최후의 생존자 {winner.mention}님이 좀비 소굴에서 홀로 탈출에 성공했습니다!",
                color=0xFFD700
            )
            await ctx.send(embed=embed)
            if ctx.voice_client and ctx.voice_client.is_playing(): ctx.voice_client.stop()
            if cid in zombie_games: del zombie_games[cid]
            return

        if not survivors:
            await ctx.send("💀 **모든 생존자가 감염되었습니다! 좀비 최종 승리!**")
            if ctx.voice_client and ctx.voice_client.is_playing(): ctx.voice_client.stop()
            if cid in zombie_games: del zombie_games[cid]
            return

        # 추격 페이즈
        await ctx.send("🩸 **[추격 페이즈]** 좀비들이 다가옵니다...")
        await asyncio.sleep(2)
        if cid not in zombie_games: return
        
        if "bgm_start_time" in data:
            data["bgm_elapsed"] = data.get("bgm_elapsed", 0) + (time.time() - data["bgm_start_time"])
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        try: await play_sound(ctx, "run2.mp3")
        except: pass
        
        has_player_zombies = any(data["is_zombie"].values())
        
        if not has_player_zombies:
            if data["round"] == 1:
                roll = random.randint(1, 6)
            else:
                roll = random.randint(1, 6) + 3
            data["ai_zombie_pos"] += roll
            await ctx.send(f"🤖 **[AI 좀비]** 주사위를 굴려 **{roll}칸** 전진! (현재: {data['ai_zombie_pos']}칸)")
            await asyncio.sleep(1.5)
            if cid not in zombie_games: return
            
            caught = []
            for p in survivors:
                if data["survivor_pos"][p.id] <= data["ai_zombie_pos"]:
                    data["is_zombie"][p.id] = True
                    data["zombie_order"].append(p.id)
                    data["zombie_pos"][p.id] = data["survivor_pos"][p.id]
                    caught.append(p)
                    data["round_new_infections"] += 1
                    
            if caught:
                if cid not in zombie_games: return
                cnames = ", ".join([p.name for p in caught])
                await ctx.send(f"😱 **앗!! {cnames}님이 잡혔습니다!! (숙주 흑화)**")
            else:
                await ctx.send("💨 아무도 잡히지 않았습니다!")
        else:
            for z_id in list(data["zombie_order"]):
                if cid not in zombie_games: return
                z_player = discord.utils.get(data['players'], id=z_id)
                if not z_player: continue
                
                view = ZombieRollView(z_id, label="주사위 굴리기 🎲")
                msg = await ctx.send(f"🧟 **[{z_player.name} 좀비]** 의 추격 턴입니다! 주사위를 굴려주세요! (30초)", view=view)
                await view.wait()
                if cid not in zombie_games: return
                await msg.edit(view=None)
                if not view.rolled:
                    await ctx.send(f"⏳ **[{z_player.name} 좀비]** 님이 주사위를 굴리지 않아 자동으로 굴립니다.")
                
                roll = random.randint(1, 6) + 3
                data["zombie_pos"][z_id] += roll
                await ctx.send(f"🧟 **[{z_player.name} 좀비]** 미친 듯이 쫓아갑니다! 주사위 **{roll}칸** 전진 (1d6+3)! (현재: {data['zombie_pos'][z_id]}칸)")
                await asyncio.sleep(1.5)
                if cid not in zombie_games: return
                
                caught = []
                cur_survs = [p for p in data["players"] if not data["is_zombie"][p.id]]
                for p in cur_survs:
                    if data["survivor_pos"][p.id] <= data["zombie_pos"][z_id]:
                        data["is_zombie"][p.id] = True
                        data["zombie_order"].append(p.id)
                        data["zombie_pos"][p.id] = data["survivor_pos"][p.id]
                        caught.append(p)
                        data["round_new_infections"] += 1
                        
                if caught:
                    cnames = ", ".join([p.name for p in caught])
                    await ctx.send(f"🩸 **끔찍합니다!! {cnames}님이 {z_player.name} 좀비에게 감염되었습니다!!**")
                else:
                    await ctx.send("💨 잡힌 사람이 없습니다.")
                await asyncio.sleep(1.5)
                if cid not in zombie_games: return

        if cid not in zombie_games: return
        final_survs = [p for p in data["players"] if not data["is_zombie"][p.id]]
        
        if len(final_survs) == 1:
            winner = final_survs[0]
            embed = discord.Embed(
                title="🏆 ZOMBIE RUN FINAL SURVIVOR",
                description=f"최후의 생존자 {winner.mention}님이 좀비 소굴에서 홀로 탈출에 성공했습니다!",
                color=0xFFD700
            )
            await ctx.send(embed=embed)
            if ctx.voice_client and ctx.voice_client.is_playing(): ctx.voice_client.stop()
            if cid in zombie_games: del zombie_games[cid]
            return

        if not final_survs:
            await ctx.send("💀 **모든 생존자가 감염되었습니다! 좀비 최종 승리!**")
            if ctx.voice_client and ctx.voice_client.is_playing(): ctx.voice_client.stop()
            if cid in zombie_games: del zombie_games[cid]
            return
            
        inf_count = data["round_new_infections"]
        if inf_count == 0:
            data["starvation"] += 1
            await ctx.send(f"🍗 **[굶주림]** 좀비들이 아무도 잡지 못해 허기집니다... 아사 스택 상승! (현재: {data['starvation']}/3)")
        else:
            data["starvation"] = 0
            await ctx.send("🍖 **[포식]** 누군가 희생된 덕분에 좀비 배가 찼습니다. 아사 스택이 0으로 초기화됩니다!")
            
        if data["starvation"] >= 3:
            await ctx.send("🎉 **좀비들이 모두 굶어 죽었습니다! 생존자 최종 승리!!**")
            if ctx.voice_client and ctx.voice_client.is_playing(): ctx.voice_client.stop()
            if cid in zombie_games: del zombie_games[cid]
            return
            
        if inf_count > 0:
            banned = []
            min_btns = 3 if len(final_survs) >= 3 else 2
            for _ in range(inf_count):
                if len(data["buttons"]) > min_btns:
                    tgt = random.choice(data["buttons"])
                    data["buttons"].remove(tgt)
                    banned.append(tgt)
            if banned:
                await ctx.send(f"🚫 **[절망]** 감염의 여파로 숫자 {banned} 버튼이 파괴되었습니다! 남은 버튼: {data['buttons']}")

        data["round"] += 1
        await ctx.send("=========================================\n")
        await asyncio.sleep(2)
        if cid not in zombie_games: return
        
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        options = f"-vn -ss {data.get('bgm_elapsed', 0)}"
        if ctx.voice_client:
            file_path = os.path.join(BASE_DIR, "run.mp3")
            ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg")
            if os.path.exists(file_path):
                try: ctx.voice_client.play(discord.FFmpegPCMAudio(file_path, options=options, executable=ffmpeg_path if os.path.exists(ffmpeg_path) else "ffmpeg"))
                except: pass
        data["bgm_start_time"] = time.time()


# ==========================================
# 📖 [비밀소설] (Secret Novel)
# ==========================================
# [지시사항]
# 1. 기존 코드(주제어, 라이어, 양세찬, 제로섬 등)를 전혀 수정하지 않고 하단에 추가합니다.
# 2. 파일 경로는 절대 경로 r"C:\정승찬\google-AI-studio\주제어BOT\비밀소설테마"를 사용합니다.
# 3. 모든 타자는 Modal(모달)을 통해 문장을 20~100자 사이로 입력합니다.
# 4. 2번 타자는 1번 타자 문장의 마지막 30%(최소 8자)만 보고 작성합니다.
# 5. 엔딩 타자는 이전 문장 전체를 보고 이야기를 끝맺습니다.
# 6. 마지막 타자(추리자)는 엔딩 문장만 보고 제시어를 4지선다 버튼으로 맞힙니다.

SECRET_NOVEL_DIR = os.path.join(BASE_DIR, "비밀소설테마")
NOVEL_BGM_DIR = os.path.join(BASE_DIR, "novel")

async def play_novel_bgm(target, filename):
    if hasattr(target, "response"): 
        author = target.user; guild = target.guild
    elif hasattr(target, "author"):
        author = target.author; guild = target.guild
    else:
        author = None; guild = target.guild

    vc = guild.voice_client
    
    if vc is None or not vc.is_connected():
        if author and getattr(author, "voice", None):
            vc = await author.voice.channel.connect()
        else:
            return 
    elif author and getattr(author, "voice", None) and vc.channel != author.voice.channel:
        await vc.move_to(author.voice.channel)

    file_path = os.path.join(NOVEL_BGM_DIR, filename)
    if not os.path.exists(file_path): return

    if vc.is_playing(): vc.stop()
    ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg")
    try:
        vc.play(discord.FFmpegPCMAudio(file_path, executable=ffmpeg_path if os.path.exists(ffmpeg_path) else "ffmpeg"))
    except: pass

secret_novel_games = {}

class SecretNovelInputModal(discord.ui.Modal):
    def __init__(self, title, label, placeholder, secret_word=None):
        super().__init__(title=title)
        self.secret_word = secret_word
        self.content = discord.ui.TextInput(
            label=label,
            style=discord.TextStyle.paragraph,
            placeholder=placeholder,
            min_length=20,
            max_length=100,
            required=True
        )
        self.add_item(self.content)
        self.result = None

    async def on_submit(self, interaction: discord.Interaction):
        if self.secret_word and self.secret_word in self.content.value:
            await interaction.response.send_message(f"❌ 규칙 위반! 비밀 제시어 '**{self.secret_word}**' 단어를 직접 쓸 수 없습니다. 버튼을 다시 눌러 수정해 주세요.", ephemeral=True)
            return

        self.result = self.content.value
        await interaction.response.send_message("✅ 문장은 정상적으로 기록되었습니다!", ephemeral=True)
        self.stop()

class SecretNovelInputView(discord.ui.View):
    def __init__(self, target_player):
        super().__init__(timeout=300.0)
        self.target_player = target_player
        self.result = None

    @discord.ui.button(label="📝 문장 작성하기 (팝업)", style=discord.ButtonStyle.primary)
    async def input_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_player.id:
            await interaction.response.send_message("❌ 지금은 당신의 차례가 아닙니다!", ephemeral=True)
            return
        
        modal = SecretNovelInputModal(title="📖 비밀소설 문장 작성", label="내용을 입력하세요 (20-100자)")
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.result:
            self.result = modal.result
            self.stop()

class SecretNovelGuessView(discord.ui.View):
    def __init__(self, guesser, correct_word, all_options, callback_func):
        super().__init__(timeout=180.0)
        self.guesser = guesser
        self.correct_word = correct_word
        self.callback_func = callback_func
        # 선택지 셔플 (정답 위치 무작위화)
        random.shuffle(all_options)
        
        for option in all_options:
            btn = discord.ui.Button(label=option, style=discord.ButtonStyle.secondary)
            btn.callback = self.make_callback(option)
            self.add_item(btn)

    def make_callback(self, choice):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.guesser:
                await interaction.response.send_message("❌ 당신은 추리자가 아닙니다!", ephemeral=True)
                return
            await self.callback_func(interaction, choice == self.correct_word, choice)
            self.stop()
        return callback

class SecretNovelJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=60.0)
        self.host = host
        self.players = [host]

    @discord.ui.button(label="🙋‍♂️ 참여하기", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        # [🛠️ 강제 업데이트: 참가자 전원 표시]
        embed.description = f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n(최소 3명 필요)"
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🚀 게임시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 3:
            await interaction.response.send_message("최소 3명 이상의 참가자가 필요합니다!", ephemeral=True)
            return

        cid = interaction.channel.id
        if cid in secret_novel_games:
            await interaction.response.send_message("❌ 이미 진행 중인 게임이 있습니다.", ephemeral=True)
            return

        await interaction.response.edit_message(content="📖 **[비밀소설]** 게임을 시작합니다!", embed=None, view=None)
        # [🛠️ 강제 업데이트: 슬라이싱 없이 전원 참가]
        await start_secret_novel(await bot.get_context(interaction.message), self.players)
        self.stop()

@bot.command(name="비밀소설")
async def cmd_secret_novel(ctx):
    cid = ctx.channel.id
    if cid in secret_novel_games:
        await ctx.send("❌ 이미 해당 채널에서 비밀소설 게임이 진행 중입니다.")
        return
    
    try: await play_sound(ctx, "intro.mp3")
    except Exception as e: print(f"🔥 오디오 에러 발생: {e}")
    
    embed = discord.Embed(title="📖 (모집 중) 미니게임 [비밀소설]", description=f"**현재 참가자:** {ctx.author.mention}\n(최소 3명 필요)", color=0x9B59B6)
    embed.add_field(name="📚 진행 방식", value="1. **1번 타자:** 비밀 단어를 보고 첫 문장 생성\n2. **2번 타자:** 문장의 **끝 30%**만 보고 이어 쓰기 (철벽 보안)\n3. **중간/엔딩 타자:** 앞 문장 전체를 보고 스토리 전개/마무리\n4. **추리자:** 마지막 문장만 보고 비밀 단어 맞히기!", inline=False)
    view = SecretNovelJoinView(ctx.author)
    await ctx.send(embed=embed, view=view)

@bot.command(name="비밀소설종료")
async def cmd_stop_secret_novel(ctx):
    cid = ctx.channel.id
    if cid in secret_novel_games:
        del secret_novel_games[cid]
        await ctx.send("🛑 비밀소설 게임을 강제 종료했습니다.")
    else:
        await ctx.send("❌ 진행 중인 비밀소설 게임이 없습니다.")

@bot.command(name="군웅할거종료")
async def cmd_stop_samguk(ctx):
    cid = ctx.channel.id
    if cid in samguk_games:
        del samguk_games[cid]
        if ctx.voice_client: await ctx.voice_client.disconnect()
        await ctx.send("🛑 군웅할거 게임을 강제 종료했습니다.")
    else:
        await ctx.send("❌ 진행 중인 군웅할거 게임이 없습니다.")

@bot.command(name="탐정종료", aliases=["수사종료"])
async def cmd_stop_detective(ctx):
    cid = ctx.channel.id
    if cid in detective_games:
        del detective_games[cid]
        await ctx.send("🛑 **탐정 수사극이 강제로 종료되었습니다.**")
    else:
        await ctx.send("⚠️ 현재 이 채널에서 진행 중인 탐정 수사극이 없습니다.")

@bot.command(name="탐정스킵")
async def cmd_detective_skip(ctx):
    cid = ctx.channel.id
    game = detective_games.get(cid)
    if not game: return
    if ctx.author.id != game.host.id:
        await ctx.send("❌ 방장만 사용 가능한 명령어입니다."); return
    
    if hasattr(game, "waiting_round_3"):
        delattr(game, "waiting_round_3")
        await ctx.send("⏩ **[방장 권한] 목격자의 힌트 제출을 강제로 스킵합니다!**")
        await start_detective_round_4(ctx.channel, cid)
    elif hasattr(game, "waiting_round_4"):
        delattr(game, "waiting_round_4")
        await ctx.send("⏩ **[방장 권한] 범행 수법 힌트 제출을 강제로 스킵합니다!**")
        await start_detective_round_5(ctx.channel, cid)
    else:
        await ctx.send("⚠️ 지금은 스킵할 수 있는 단계(힌트 대기 중)가 아닙니다.")

async def start_secret_novel(ctx, players):
    cid = ctx.channel.id
    categories = ["감정", "아이템", "장르", "장소"]
    category = random.choice(categories)
    file_path = os.path.join(SECRET_NOVEL_DIR, f"{category}.txt")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            words = [line.strip() for line in f if line.strip()]
        if not words: raise Exception("단어 목록이 비어 있습니다.")
    except Exception as e:
        await ctx.send(f"❌ 단어 파일을 로드하는 중 오류 발생: {e}\n(경로 확인: {SECRET_NOVEL_DIR})")
        return

    # [🛠️ 강제 업데이트: 플레이어 셔플 및 인원 제한 제거]
    players = random.sample(players, len(players))
    secret_word = random.choice(words)
    other_words = [w for w in words if w != secret_word]
    wrong_options = random.sample(other_words, min(len(other_words), 3))
    all_options = [secret_word] + wrong_options
    random.shuffle(all_options) # 정답 위치 무작위화

    secret_novel_games[cid] = {
        "players": players,
        "sentences": [],
        "secret_word": secret_word,
        "category": category,
        "all_options": all_options
    }

    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
    await play_novel_bgm(ctx, "novel.mp3")


    authors = players[:-1]
    guesser = players[-1]
    
    order_text = " ➔ ".join([p.name for p in authors])
    start_msg = (
        f"🎬 **소설 작성을 시작합니다!**\n"
        f"✍️ **작가 순서:** {order_text}\n"
        f"🕵️ **최종 추리자:** {guesser.name}"
    )
    await ctx.send(start_msg)
    await asyncio.sleep(2)

    for i, p in enumerate(players):
        if cid not in secret_novel_games: return
        
        # 마지막 플레이어는 추리자이므로 루프 종료
        if i == len(players) - 1:
            break

        hint_embed = discord.Embed(title=f"📝 {p.name} 작가님 차례 ({i+1}/{len(players)-1})", color=0x9B59B6)
        
        if i == 0:
            hint_embed.title = f"📝 {p.name} 작가님 차례 [최초 작성자]"
            hint_embed.description = "🤫 당신은 **[최초 작성자]**입니다.\n아래 버튼을 눌러 **비밀 제시어**를 확인하고 첫 문장을 작성해 주세요!"
            m_title = "📖 비밀소설: 최초 작성"
            m_label = f"비밀 제시어: {secret_word} ({category})"
            m_placeholder = "여기에 첫 문장을 작성하세요..."
        elif i == 1:
            # 2번 타자는 무조건 30% 보안 힌트 적용
            hint_embed.title = f"📝 {p.name} 작가님 차례 [보안 릴레이]"
            prev = secret_novel_games[cid]["sentences"][i-1]
            s_len = max(8, int(len(prev) * 0.3))
            
            pos_type = random.choice(["front", "middle", "back"])
            if pos_type == "front":
                end_idx = s_len
                while end_idx < len(prev) and prev[end_idx] != ' ': end_idx += 1
                visible = prev[:end_idx].strip()
                hint_format = f"{visible} ..."
            elif pos_type == "middle":
                start_idx = len(prev) // 2 - s_len // 2
                while start_idx > 0 and prev[start_idx - 1] != ' ': start_idx -= 1
                end_idx = start_idx + s_len
                while end_idx < len(prev) and prev[end_idx] != ' ': end_idx += 1
                visible = prev[start_idx:end_idx].strip()
                hint_format = f"... {visible} ..."
            else: # back
                start_idx = len(prev) - s_len
                while start_idx > 0 and prev[start_idx - 1] != ' ': start_idx -= 1
                visible = prev[start_idx:].strip()
                hint_format = f"... {visible}"
            
            hint_embed.description = "🔒 **[철벽 보안 룰]**이 적용되었습니다.\n아래 버튼을 눌러 **무작위 보안 힌트(30%)**를 확인하고 문장을 이어주세요!"
            m_title = "📖 비밀소설: 보안 릴레이"
            m_label = f"힌트: {hint_format}"[:45]
            m_placeholder = f"{hint_format}\n(위 내용을 바탕으로 문장을 이어가 주세요)"
        elif i == len(players) - 2:
            # 마지막 작가 (추리자 바로 앞)
            hint_embed.title = f"📝 {p.name} 작가님 차례 [엔딩 작가]"
            prev = secret_novel_games[cid]["sentences"][i-1]
            hint_embed.description = "🎬 당신은 **[마지막 소설가]**입니다.\n아래 버튼을 눌러 **앞 문장**을 확인하고 이야기를 마무리해 주세요!"
            m_title = "📖 비밀소설: 엔딩 작성"
            m_label = "앞 문장을 확인하고 이어주세요 ↓"
            m_placeholder = prev
        else:
            # 그 외 모든 중간 작가들
            hint_embed.title = f"📝 {p.name} 작가님 차례 [릴레이 작가]"
            prev = secret_novel_games[cid]["sentences"][i-1]
            hint_embed.description = "✍️ 소설 작가 차례입니다.\n아래 버튼을 눌러 **앞 문장**을 확인하고 내용을 이어가 주세요!"
            m_title = "📖 비밀소설: 스토리 이어가기"
            m_label = "앞 문장을 확인하고 이어주세요 ↓"
            m_placeholder = prev

        class SecretNovelTaskView(discord.ui.View):
            def __init__(self, target_player, title, label, placeholder, secret_word=None):
                super().__init__(timeout=300.0)
                self.target_player = target_player
                self.m_title = title[:45]
                self.m_label = label[:45]
                self.m_placeholder = placeholder[:100]
                self.secret_word = secret_word
                self.result = None

            @discord.ui.button(label="📝 문장 작성하기 (팝업)", style=discord.ButtonStyle.primary)
            async def input_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.target_player.id:
                    await interaction.response.send_message("❌ 지금은 당신의 차례가 아닙니다!", ephemeral=True)
                    return
                modal = SecretNovelInputModal(self.m_title, self.m_label, self.m_placeholder, secret_word=self.secret_word)
                await interaction.response.send_modal(modal)
                await modal.wait()
                if cid not in secret_novel_games: return
                if modal.result:
                    self.result = modal.result
                    self.stop()

        view = SecretNovelTaskView(p, m_title, m_label, m_placeholder, secret_word=secret_word)
        msg = await ctx.send(f"{p.mention} 작가님, 아래 버튼을 눌러 모달 창을 열어주세요! (제한시간 5분)", embed=hint_embed, view=view)
        
        await view.wait()
        if cid not in secret_novel_games: return
        if not view.result:
            await ctx.send(f"⌛ **[시간 초과]** {p.name} 작가님이 응답하지 않아 게임이 중단되었습니다.")
            if ctx.voice_client: await ctx.voice_client.disconnect()
            if cid in secret_novel_games: del secret_novel_games[cid]
            return
        
        secret_novel_games[cid]["sentences"].append(view.result)
        await msg.edit(content=f"✅ {p.name} 작가님의 문장이 등록되었습니다!", embed=None, view=None)
        await asyncio.sleep(1)

    if cid not in secret_novel_games: return
    guesser = players[-1]
    last_s = secret_novel_games[cid]["sentences"][-1]
    
    guess_embed = discord.Embed(
        title=f"🕵️ 마지막 단계: [추리자] {guesser.name}님", 
        description=f"추리자 {guesser.name}님은 마지막 엔딩 문장만 보고 **최초 제시어**가 무엇인지 맞혀야 합니다!\n\n**[도착한 엔딩 문장]**\n`{last_s}`", 
        color=0xE91E63
    )
    
    async def guess_done(interaction, correct, chosen_word):
        if cid not in secret_novel_games:
            await interaction.response.send_message("❌ 이미 종료된 게임입니다.", ephemeral=True)
            return

        full_story_discord = ""
        full_story_raw = ""
        for idx, text in enumerate(secret_novel_games[cid]["sentences"]):
            writer_name = players[idx].name
            full_story_discord += f"**{idx+1}번({writer_name}):** {text}\n"
            full_story_raw += f"{idx+1}번({writer_name}): {text}\n"

        res_color = 0x2ECC71 if correct else 0xE74C30
        res_title = "🎊 [정답!] 추리 성공" if correct else "❌ [오답] 추리 실패"

        final_embed = discord.Embed(title=res_title, color=res_color)
        final_embed.set_author(name=f"추리자: {guesser.name}")

        # 2000자 초과 또는 필드 제한(1024자) 초과 시 파일로 전송
        file = None
        if len(full_story_discord) > 1024:
            final_embed.add_field(name="📜 원본 소설 로그", value="📜 소설 내용이 길어 파일로 첨부합니다.", inline=False)
            file = discord.File(io.BytesIO(full_story_raw.encode("utf-8")), filename="secret_novel.txt")
        else:
            final_embed.add_field(name="📜 원본 소설 로그", value=full_story_discord, inline=False)

        final_embed.add_field(name="🔑 원래 제시어", value=f"**{secret_word}** ({category})", inline=True)
        final_embed.add_field(name="🎯 결과", value=f"{guesser.mention}님은 **[{chosen_word}]**을(를) 골랐습니다!\n({'정답입니다! 🎉' if correct else '오답입니다... ❌'})", inline=True)

        await interaction.response.edit_message(content="✨ **비밀소설 게임 결과 발표!**", embed=final_embed, view=None)
        if file:
            await interaction.followup.send(file=file)

        # 여기서 승패 브금 재생
        if correct:
            await play_novel_bgm(interaction, "carry.mp3")
        else:
            await play_novel_bgm(interaction, "GG.mp3")

        if cid in secret_novel_games: del secret_novel_games[cid]


    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
    try: await play_sound(ctx, "judgment.mp3")
    except: pass

    guess_view = SecretNovelGuessView(guesser, secret_word, secret_novel_games[cid]["all_options"], guess_done)
    await ctx.send(f"{guesser.mention}님, 최초의 문장을 장식했던 비밀 단어는 무엇일까요? (4지선다)", embed=guess_embed, view=guess_view)

# ==========================================
# 🏯 [삼국지: 군웅할거] (Three Kingdoms: War)
# ==========================================
samguk_games = {}

KINGDUM_BGM_DIR = os.path.join(BASE_DIR, "Kingdum_bgm")

async def play_samguk_bgm(target, filename):
    if hasattr(target, "response"): 
        author = target.user; guild = target.guild
    elif hasattr(target, "author"):
        author = target.author; guild = target.guild
    else:
        author = None; guild = target.guild

    vc = guild.voice_client
    
    # [핵심] 봇이 음성방에 없거나 연결이 끊겨있으면 강제 재연결
    if vc is None or not vc.is_connected():
        if author and getattr(author, "voice", None):
            vc = await author.voice.channel.connect()
        else:
            return # 연결할 대상이 없으면 포기
    elif author and getattr(author, "voice", None) and vc.channel != author.voice.channel:
        await vc.move_to(author.voice.channel)

    file_path = os.path.join(KINGDUM_BGM_DIR, filename)
    if not os.path.exists(file_path): 
        print(f"BGM 파일 없음: {file_path}")
        return

    if vc.is_playing(): vc.stop()

    def after_playing(error):
        if filename == "sortie.mp3":
            bot.loop.create_task(play_samguk_bgm(target, "battle.mp3"))

    ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg")
    try:
        vc.play(discord.FFmpegPCMAudio(file_path, executable=ffmpeg_path if os.path.exists(ffmpeg_path) else "ffmpeg"), after=after_playing)
    except: pass





class SamgukPlayer:
    def __init__(self, user):
        self.user = user
        self.user_id = user.id
        self.name = user.display_name # [🛠️ 수정 1] 닉네임(display_name) 사용
        self.country_name = f"{user.display_name} 나라"
        self.troops = 17

        self.is_alive = True
        self.secret_letters = []  # List of dicts: {"sender_id": id, "sender_name": name, "content": text}
        self.replies_received = [] # [🛠️ 수정 1] 내가 보낸 사신에 대한 답장 저장 리스트 추가
        self.sent_count = 0 
        self.messages_received_this_round = []

class SamgukGame:
    def __init__(self, cid, host, players):
        self.cid = cid
        self.host = host
        self.players = players  # Dict {user_id: SamgukPlayer}
        self.round = 1
        self.actions = {}  # Dynamic data per phase
        self.expected_actions = 0 # 페이즈별 관리용
        self.log = []

    def get_alive_players(self):
        return [p for p in self.players.values() if p.is_alive]

# --- 외교 페이즈 R1: 밀서 발송 ---
class SamgukDiplomacyView(discord.ui.View):
    def __init__(self, cid, players):
        super().__init__(timeout=None)
        self.cid = cid
        for p in players:
            btn = discord.ui.Button(label=f"📜 [{p.country_name}]", style=discord.ButtonStyle.secondary)
            btn.callback = self.make_send_callback(p.user_id)
            self.add_item(btn)
        
        done_btn = discord.ui.Button(label="✅ 턴 완료", style=discord.ButtonStyle.green)
        done_btn.callback = self.done_callback
        self.add_item(done_btn)

    def make_send_callback(self, target_id):
        async def callback(interaction: discord.Interaction):
            game = samguk_games.get(self.cid)
            if not game: return
            me = game.players.get(interaction.user.id)
            if not me or not me.is_alive:
                await interaction.response.send_message("❌ 생존자만 참여할 수 있습니다.", ephemeral=True)
                return
            if interaction.user.id == target_id:
                await interaction.response.send_message("❌ 자신에게는 보낼 수 없습니다.", ephemeral=True)
                return
            if game.actions.get(interaction.user.id):
                await interaction.response.send_message("❌ 이미 턴을 완료했습니다.", ephemeral=True)
                return
            if me.troops < 1:
                await interaction.response.send_message("❌ 병력이 부족하여 사신을 보낼 수 없습니다.", ephemeral=True)
                return
            
            modal = SamgukMessageModal(self.cid, target_id)
            await interaction.response.send_modal(modal)
        return callback

    async def done_callback(self, interaction: discord.Interaction):
        game = samguk_games.get(self.cid)
        if not game: return
        me = game.players.get(interaction.user.id)
        if not me or not me.is_alive:
            await interaction.response.send_message("❌ 생존자만 참여할 수 있습니다.", ephemeral=True)
            return
        if game.actions.get(interaction.user.id):
            await interaction.response.send_message("❌ 이미 턴을 완료했습니다.", ephemeral=True)
            return

        game.actions[interaction.user.id] = True
        await interaction.response.send_message("✅ 외교 턴을 완료했습니다.", ephemeral=True)

        if len(game.actions) == len(game.get_alive_players()):
            channel = bot.get_channel(self.cid)
            await channel.send("📢 모든 군주가 외교를 마쳤습니다!")
            await start_samguk_round(channel, self.cid, game.round + 1)

class SamgukDiplomacyR2View(discord.ui.View):
    def __init__(self, cid):
        super().__init__(timeout=None)
        self.cid = cid

    @discord.ui.button(label="📜 도착한 밀서 확인", style=discord.ButtonStyle.secondary)
    async def view_letters(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = samguk_games.get(self.cid)
        if not game: return
        me = game.players.get(interaction.user.id)
        if not me or not me.is_alive:
            await interaction.response.send_message("❌ 생존 군주만 확인 가능합니다.", ephemeral=True)
            return
        
        if not me.secret_letters:
            await interaction.response.send_message("📭 도착한 밀서가 없습니다.", ephemeral=True)
            return
        
        view = SamgukReplyView(self.cid, interaction.user.id, me.secret_letters)
        await interaction.response.send_message(f"📧 **{len(me.secret_letters)}통의 밀서가 도착했습니다.**", view=view, ephemeral=True)

    @discord.ui.button(label="✅ 판결 완료", style=discord.ButtonStyle.green)
    async def finish_turn(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = samguk_games.get(self.cid)
        if not game: return
        me = game.players.get(interaction.user.id)
        if not me or not me.is_alive:
            await interaction.response.send_message("❌ 생존 군주만 가능합니다.", ephemeral=True)
            return
        
        if game.actions.get(interaction.user.id):
            await interaction.response.send_message("❌ 이미 판결을 마쳤습니다.", ephemeral=True)
            return
            
        game.actions[interaction.user.id] = True
        await interaction.response.send_message("✅ 외교 턴을 완료했습니다.", ephemeral=True)

        if len(game.actions) == len(game.get_alive_players()):
            channel = bot.get_channel(self.cid)
            await channel.send("📢 모든 군주가 판결을 마쳤습니다!")
            for p in game.get_alive_players(): 
                p.troops += 3
                p.secret_letters = []
            await start_samguk_round(channel, self.cid, game.round + 1)

class SamgukMessageModal(discord.ui.Modal, title="📜 외교 밀서 작성"):
    content = discord.ui.TextInput(label="내용", style=discord.TextStyle.paragraph, placeholder="사신에게 들려보낼 메시지를 입력하세요...", min_length=1, max_length=200)
    
    def __init__(self, cid, target_id):
        super().__init__()
        self.cid = cid
        self.target_id = target_id

    async def on_submit(self, interaction: discord.Interaction):
        game = samguk_games.get(self.cid)
        if not game: return
        
        sender = game.players[interaction.user.id]
        target = game.players[self.target_id]
        
        sender.troops -= 1
        target.secret_letters.append({"sender_id": sender.user_id, "sender_name": sender.country_name, "content": self.content.value})
        
        await interaction.response.send_message(f"✅ 사신을 보냈습니다.", ephemeral=True)

# --- 외교 페이즈 R2: 답장 및 처형 ---
class SamgukReplyModal(discord.ui.Modal, title="📜 외교 답장 작성"):
    content = discord.ui.TextInput(label="답장 내용", style=discord.TextStyle.paragraph, placeholder="상대방에게 보낼 텍스트를 적어주세요...", required=True, min_length=1, max_length=200)

    def __init__(self, cid, sender_id, is_kill, user_id, idx):
        super().__init__()
        self.cid = cid
        self.sender_id = sender_id
        self.is_kill = is_kill
        self.user_id = user_id
        self.idx = idx

    async def on_submit(self, interaction: discord.Interaction):
        game = samguk_games.get(self.cid)
        if not game: return
        
        me = game.players[interaction.user.id]
        sender = game.players[self.sender_id]
        
        status_text = "💀 당신의 사신은 처형당했습니다." if self.is_kill else "🕊️ 사신이 무사히 돌아왔습니다."
        if not self.is_kill:
            sender.troops += 1 # 병력 복구

        # [🛠️ 수정 3] 상대방의 replies_received에 결과 저장
        sender.replies_received.append({
            "from": me.country_name,
            "content": self.content.value,
            "is_kill": self.is_kill
        })

        reply_msg = f"📜 **[{me.country_name}]의 답장:**\n{self.content.value}\n\n{status_text}"
        
        try:
            await sender.user.send(reply_msg)
        except:
            pass 

        await interaction.response.send_message(f"✅ 판결과 답장을 보냈습니다. ({'처형' if self.is_kill else '귀환'})", ephemeral=True)

class SamgukReplyView(discord.ui.View):
    def __init__(self, cid, user_id, letters):
        super().__init__(timeout=None)
        self.cid = cid
        self.user_id = user_id
        for i, letter in enumerate(letters):
            btn = discord.ui.Button(label=f"[{letter['sender_name']}] 판결", style=discord.ButtonStyle.secondary, custom_id=f"reply_{i}")
            btn.callback = self.make_callback(letter, i)
            self.add_item(btn)

    def make_callback(self, letter, idx):
        async def callback(interaction: discord.Interaction):
            view = SamgukJudgementView(self.cid, self.user_id, letter, idx)
            await interaction.response.send_message(f"📜 **{letter['sender_name']}의 밀서:**\n{letter['content']}\n\n사신을 어떻게 대우하시겠습니까?", view=view, ephemeral=True)
        return callback

class SamgukJudgementView(discord.ui.View):
    def __init__(self, cid, user_id, letter, idx):
        super().__init__(timeout=None)
        self.cid = cid
        self.user_id = user_id
        self.letter = letter
        self.idx = idx

    @discord.ui.button(label="🕊️ 무사 귀환 (병력 복구)", style=discord.ButtonStyle.green)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SamgukReplyModal(self.cid, self.letter['sender_id'], False, self.user_id, self.idx)
        await interaction.response.send_modal(modal)
        await interaction.edit_original_response(content="✅ 사신 대우 방침을 결정했습니다. (답장 작성 중...)", view=None)

    @discord.ui.button(label="🔪 사신 처형 (병력 손실)", style=discord.ButtonStyle.red)
    async def kill(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SamgukReplyModal(self.cid, self.letter['sender_id'], True, self.user_id, self.idx)
        await interaction.response.send_modal(modal)
        await interaction.edit_original_response(content="✅ 사신 대우 방침을 결정했습니다. (답장 작성 중...)", view=None)

class SamgukWarMainView(discord.ui.View):
    def __init__(self, cid):
        super().__init__(timeout=None)
        self.cid = cid
    
    @discord.ui.button(label="📩 내가 받은 답장 확인", style=discord.ButtonStyle.secondary)
    async def check_replies(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = samguk_games.get(self.cid)
        if not game: return
        me = game.players.get(interaction.user.id)
        if not me or not me.is_alive: return

        if not me.replies_received:
            await interaction.response.send_message("📨 아직 도착한 답장이 없습니다.", ephemeral=True)
            return
        
        msg = "📩 **[지난 외교의 결과]**\n"
        for r in me.replies_received:
            status = "💀 사신 처형당함" if r['is_kill'] else "🕊️ 사신 귀환함"
            msg += f"🚩 **{r['from']}**: {r['content']}\n({status})\n\n"
        
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="⚔️ 병력 배치 및 출정", style=discord.ButtonStyle.primary)
    async def start_distribution(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = samguk_games.get(self.cid)
        if not game: return
        me = game.players.get(interaction.user.id)
        if not me or not me.is_alive: return
        
        if game.actions.get(interaction.user.id):
            await interaction.response.send_message("❌ 이미 배치를 완료했습니다.", ephemeral=True)
            return

        alive = game.get_alive_players()
        v = discord.ui.View()
        v.add_item(SamgukWarTargetSelect(self.cid, alive, interaction.user.id))
        await interaction.response.send_message("⚔️ 공격할 대상들을 선택하세요 (최대 3곳)", view=v, ephemeral=True)

# --- 전쟁 페이즈: 분배 ---
class SamgukWarTargetSelect(discord.ui.Select):
    def __init__(self, cid, players, user_id):
        self.cid = cid
        options = [discord.SelectOption(label=f"{p.country_name}", value=str(p.user_id)) 
                   for p in players if p.user_id != user_id]
        super().__init__(placeholder="공격할 국가들을 선택하세요 (최대 3곳)", min_values=1, max_values=min(3, len(options)), options=options)

    async def callback(self, interaction: discord.Interaction):
        game = samguk_games.get(self.cid)
        if not game:
            await interaction.response.send_message("❌ 게임이 이미 종료되었습니다.", ephemeral=True)
            return
        targets = [game.players[int(tid)] for tid in self.values]
        modal = SamgukWarDistributeModal(self.cid, targets, game.players[interaction.user.id].troops)
        await interaction.response.send_modal(modal)

class SamgukWarDistributeModal(discord.ui.Modal, title="⚔️ 군대 배치 및 출정"):
    def __init__(self, cid, targets, total_troops):
        super().__init__()
        self.cid = cid
        self.targets = targets
        self.total_troops = total_troops
        self.add_item(discord.ui.TextInput(label="🛡️ 방어 병력", placeholder=f"현재 총 병력: {total_troops}", required=True))
        self.add_item(discord.ui.TextInput(label="🌾 육성 병력", placeholder="농사/훈련", required=True))
        for t in targets:
            self.add_item(discord.ui.TextInput(label=f"⚔️ {t.country_name} 파견", placeholder="공격 병력", required=False))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            vals = [int(item.value) if item.value else 0 for item in self.children]
            if any(v < 0 for v in vals):
                await interaction.response.send_message("❌ 음수는 입력할 수 없습니다!", ephemeral=True)
                return
                
            defense = vals[0]
            cultivation = vals[1]
            attacks = vals[2:]
            
            if sum(vals) > self.total_troops:
                await interaction.response.send_message(f"❌ 병력이 부족합니다! (총 {self.total_troops}명 중 {sum(vals)}명 배치 시도)", ephemeral=True)
                return
            
            game = samguk_games.get(self.cid)
            player = game.players[interaction.user.id]
            player.actions = {"defense": defense, "attacks": {self.targets[i].user_id: attacks[i] for i in range(len(self.targets))}}
            player.actions["cultivation"] = cultivation
            
            await interaction.response.send_message(f"⚔️ 배치가 완료되었습니다. (방어: {defense}, 공격: {sum(attacks)}, 육성: {player.actions['cultivation']})", ephemeral=True)
            game.actions[player.user_id] = True
            
            if len(game.actions) == len(game.get_alive_players()):
                main_channel = bot.get_channel(self.cid)
                await main_channel.send("🔥 **모든 군주가 출정 명령을 내렸습니다! 연산을 시작합니다.**")
                await process_samguk_war(main_channel, game.cid)
        except ValueError:
            await interaction.response.send_message("❌ 숫자만 입력 가능합니다.", ephemeral=True)

# --- 전투 연산 엔진 ---
async def process_samguk_war(channel, cid):
    game = samguk_games.get(cid)
    if not game: return
    
    alive = game.get_alive_players()
    incoming = {p.user_id: 0 for p in alive}
    attackers_on = {p.user_id: [] for p in alive}
    
    for p in alive:
        for target_id, count in p.actions["attacks"].items():
            actual_atk = max(0, count - 1)  # 원정 피로도 페널티 (1명 사망)
            incoming[target_id] += actual_atk
            if actual_atk > 0:
                attackers_on[target_id].append({"id": p.user_id, "count": actual_atk})


    # 전투 연산을 위해 모든 플레이어의 병력을 0으로 초기화하고 생존자/약탈품만 다시 합산
    for p in alive: p.troops = 0

    await play_samguk_bgm(channel, "sortie.mp3")
    results = []
    for p in alive:
        total_atk = incoming[p.user_id]
        defense = p.actions["defense"]
        cult = p.actions["cultivation"]
        
        # [🛠️ 수정 3] 침략군 명단 생성
        atk_detail_list = [f"{game.players[atk['id']].country_name}({atk['count']}명)" for atk in attackers_on[p.user_id]]
        atk_detail = ", ".join(atk_detail_list) if atk_detail_list else "없음"

        if defense >= total_atk:
            surviving_def = defense - total_atk
            p.troops += (surviving_def + (cult * 3))
            results.append(f"🏰 **[{p.country_name}의 성벽]** (방어: {defense}명) 🆚 침략군: {atk_detail}\n👉 **수성 성공!** (적군 전멸, 육성 3배 ➡️ 현재 {p.troops}명)\n")
        else:
            p.is_alive = False
            loot_total = cult // 2
            loss_total = defense
            results.append(f"🔥 **[{p.country_name}의 성벽]** (방어: {defense}명) 🆚 침략군: {atk_detail}\n👉 **성문 돌파 및 함락!** (국가 멸망 및 전리품 약탈 발생)\n")
            
            if attackers_on[p.user_id]:
                total_sent = total_atk
                sorted_attackers = sorted(attackers_on[p.user_id], key=lambda x: x["count"], reverse=True)
                distributed_loss = 0
                distributed_loot = 0
                
                for entry in attackers_on[p.user_id]:
                    share = entry["count"] / total_sent
                    loss = int(loss_total * share)
                    loot = int(loot_total * share)
                    
                    attacker_p = game.players[entry["id"]]
                    surviving = entry["count"] - loss
                    attacker_p.troops += (surviving + loot) # 생존자와 전리품 합산
                    
                    distributed_loss += loss
                    distributed_loot += loot
                    
                leader_p = game.players[sorted_attackers[0]["id"]]
                extra_loss = loss_total - distributed_loss
                extra_loot = loot_total - distributed_loot
                leader_p.troops -= extra_loss
                leader_p.troops += extra_loot

    for p in alive: p.replies_received = [] # [🛠️ 수정 4] 3라운드 연산 종료 후 모든 유저 소식 초기화

    await channel.send("\n".join(results))
    await asyncio.sleep(3)
    
    if len(game.get_alive_players()) <= 1:
        winner = game.get_alive_players()[0] if game.get_alive_players() else None
        await channel.send(f"🏆 **천하통일! 최종 승리자: {winner.country_name if winner else '없음'}**")
        if channel.guild.voice_client: await channel.guild.voice_client.disconnect()
        del samguk_games[cid]
        return

    await start_samguk_round(channel, cid, game.round + 1)

async def start_samguk_round(channel, cid, r_num):
    game = samguk_games.get(cid)
    if not game or r_num > 12: 
        if game: 
            await channel.send("🏁 12라운드가 종료되었습니다. 최종 승리자가 결정되지 않았습니다.")
            if channel.guild.voice_client: await channel.guild.voice_client.disconnect()
            del samguk_games[cid]
        return
    
    game.round = r_num
    game.actions = {}
    alive = game.get_alive_players()
    
    season = (r_num - 1) // 4 + 1
    phase = "외교" if r_num in [1, 2, 5, 6, 9, 10] else "전쟁"
    
    embed = discord.Embed(title=f"🚩 [삼국지: 군웅할거] ROUND {r_num} ({season}시즌 - {phase})", color=0xD4AF37)
    status = "\n".join([f"**{p.country_name}** ({p.name}): {p.troops}명" for p in alive])
    embed.add_field(name="📊 국가 현황", value=status, inline=False)
    
    if r_num in [1, 5, 9]:
        embed.description = "📬 **외교 페이즈: 밀서 발송**\n사신을 보내 동맹을 제안하거나 기만하세요. (병력 -1 소모, 다음 라운드에서 결과 확인)"
        view = SamgukDiplomacyView(cid, alive)
        await channel.send("📬 **[외교 페이즈]** 각 국가 버튼을 눌러 밀서를 작성하세요. 작성을 마쳤거나 보낼 편지가 없다면 반드시 **[✅ 턴 완료]**를 누르세요!", view=view)
        await channel.send(embed=embed)
    elif r_num in [2, 6, 10]:
        embed.description = "📧 **외교 페이즈: 수신 확인 및 판결**\n사신을 살려 보낼지, 목을 벨지 결정하세요. (종료 시 전원 +3명 징병)"
        game.expected_actions = sum(len(p.secret_letters) for p in alive)
        view = SamgukDiplomacyR2View(cid)
        await channel.send("📧 **[외교 페이즈]** [📜 도착한 밀서 확인] 버튼을 눌러 판결을 내린 뒤, 반드시 **[✅ 판결 완료]**를 누르세요!", view=view)
        await channel.send(embed=embed)
        if game.expected_actions == 0:
            for p in alive: p.troops += 3
            await channel.send("📢 **이번 라운드에 수신된 밀서가 없습니다. 즉시 다음으로 이동합니다.**")
            await start_samguk_round(channel, cid, r_num + 1)
    else: # 전쟁 페이즈 (3, 4, 7, 8, 11, 12)
        embed.description = "⚔️ **전쟁 페이즈: 병력 배치**\n타겟을 고르고 병력을 나누세요. 육성(남는) 병력은 성공 시 3배로 돌아옵니다!"
        view = SamgukWarMainView(cid)
        await channel.send("⚔️ **[전쟁 페이즈]** 아래 버튼을 눌러 지난 외교의 답변을 확인하고 병력을 배치하세요!", view=view)
        await channel.send(embed=embed)

@bot.command(name="군웅할거룰", aliases=["군웅할거설명", "군웅규칙"])
async def cmd_samguk_rules(ctx):
    embed = discord.Embed(title="🏯 [삼국지: 군웅할거] 상세 가이드북", description="천하를 통일하기 위한 군주들의 필수 지침서입니다.", color=0xD4AF37)
    
    embed.add_field(name="📜 1. 게임 개요", 
                    value="총 **12라운드** 동안 진행되며, 마지막까지 살아남는 최후의 1인(국가)이 승리합니다.\n기본 병력 **17명**으로 시작합니다.", inline=False)
    
    embed.add_field(name="🕊️ 2. 외교 페이즈 (1, 2, 5, 6, 9, 10 라운드)", 
                    value="**[밀서 발송]** 병력 1명을 사신으로 보내 다른 국가에 몰래 편지를 보냅니다.\n"
                          "**[판결]** 받은 사신을 **'귀환'**시키면 보낸 이의 병력이 1명 복구되고, **'처형'**하면 그대로 잃습니다.\n"
                          "👉 *판결 라운드가 끝날 때마다 살아남은 모든 군주는 **+3명의 징병(보너스)**을 받습니다.*", inline=False)
    
    embed.add_field(name="⚔️ 3. 전쟁 페이즈 - 병력 배치", 
                    value="자신의 모든 병력을 **[방어], [육성], [공격(최대 3곳)]**으로 자유롭게 분배합니다.\n"
                          "*(예: 총 20명일 때 ➔ 방어 10, 육성 5, 촉 공격 5)*", inline=False)
    
    embed.add_field(name="🔥 4. 전투 연산 룰 (매우 중요)", 
                    value="**🛡️ 수성 성공 (방어 병력 ≧ 쳐들어온 적군 총합)**\n"
                          "적군을 전멸시키며, 내가 투자했던 **[육성 병력이 3배로 뻥튀기]** 되어 돌아옵니다!\n\n"
                          "**💥 수성 실패 (방어 병력 < 쳐들어온 적군 총합)**\n"
                          "국가가 즉시 **멸망**합니다. 공격에 성공한 연합군들은 기여도에 따라 멸망한 국가의 육성 병력을 탈취(약탈)해 갑니다.\n\n"
                          "**⚠️ 원정 페널티 (행군 중 1명 사망)**\n"
                          "공격을 보낼 때 거리가 멀어 **무조건 1명이 사망한 채로 도착**합니다. 1명만 보내면 성벽에 닿기도 전에 죽어버리니 주의하세요!", inline=False)
    
    embed.set_footer(text="눈치와 배신, 그리고 완벽한 병력 배분으로 천하를 통일하세요!")
    await ctx.send(embed=embed)

@bot.command(name="군웅할거")
async def cmd_samguk(ctx):
    if ctx.channel.id in samguk_games:
        await ctx.send("❌ 이미 진행 중입니다."); return
        
    if not ctx.author.voice:
        await ctx.send("❌ 먼저 음성 채널에 접속해 주세요!"); return
        
    # 위에서 만든 만능 함수가 알아서 접속하고 노래를 틈
    await play_samguk_bgm(ctx, "opening.mp3")
    
    view = SamgukJoinView(ctx.author)
    await ctx.send(embed=discord.Embed(title="🏯 삼국지: 군웅할거 모집", description="천하패권을 차지할 군주들을 모집합니다. (최소 2명)\n\n입장 시 자신의 **국가명**을 적어주세요!", color=0xD4AF37), view=view)



class SamgukJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=60.0)
        self.host = host
        self.players = {} # user_id: user_object

    @discord.ui.button(label="🚩 참여하기", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        
        self.players[interaction.user.id] = interaction.user
        await interaction.response.send_message(f"✅ **{interaction.user.display_name} 나라** 건설 완료!", ephemeral=True)
        
        # 참여자 목록 업데이트
        embed = interaction.message.embeds[0]
        player_names = [user.display_name for user in self.players.values()]
        embed.description = f"**현재 군주:** {', '.join(player_names)}"
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="🚀 게임 시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message("방장만 가능합니다.", ephemeral=True); return
        if len(self.players) < 2:
            await interaction.response.send_message("최소 2명이 필요합니다.", ephemeral=True); return
            
        game = SamgukGame(interaction.channel_id, self.host, {uid: SamgukPlayer(user) for uid, user in self.players.items()})
        samguk_games[interaction.channel_id] = game
        await play_samguk_bgm(interaction, "battle.mp3")
        await interaction.response.edit_message(content="🏯 **군웅할거의 시대가 열렸습니다!**", embed=None, view=None)
        await start_samguk_round(interaction.channel, interaction.channel_id, 1)




@bot.command(name="군웅스킵")
async def cmd_samguk_skip(ctx):
    cid = ctx.channel.id
    game = samguk_games.get(cid)
    if not game: return
    if ctx.author.id != game.host.id:
        await ctx.send("❌ 방장만 사용 가능한 명령어입니다."); return
    
    alive = game.get_alive_players()
    r_num = game.round
    
    if r_num in [1, 5, 9]:
        for p in alive:
            if p.user_id not in game.actions:
                game.actions[p.user_id] = True
        await ctx.send("⏩ **밀서 발송 단계를 강제 종료합니다.**")
        await start_samguk_round(ctx.channel, cid, r_num + 1)
    elif r_num in [2, 6, 10]:
        await ctx.send("⏩ **판결 단계를 강제 종료합니다.**")
        for p in alive: p.troops += 3
        await start_samguk_round(ctx.channel, cid, r_num + 1)
    else: # 전쟁
        for p in alive:
            if p.user_id not in game.actions:
                p.actions = {"defense": p.troops, "attacks": {}, "cultivation": 0}
                game.actions[p.user_id] = True
        await ctx.send("⏩ **병력 배치 단계를 강제 종료합니다.**")
        await process_samguk_war(ctx.channel, cid)


# ==========================================
# 🔍 [탐정 수사극] (Detective Investigation)
# ==========================================
DETECTIVE_BGM_DIR = os.path.join(BASE_DIR, "탐정")

async def play_detective_bgm(target, filename):
    if hasattr(target, "response"): 
        author = target.user; guild = target.guild
    elif hasattr(target, "author"):
        author = target.author; guild = target.guild
    else:
        author = None; guild = target.guild

    vc = guild.voice_client
    if vc is None or not vc.is_connected():
        if author and getattr(author, "voice", None):
            vc = await author.voice.channel.connect()
        else:
            return 
    elif author and getattr(author, "voice", None) and vc.channel != author.voice.channel:
        await vc.move_to(author.voice.channel)

    file_path = os.path.join(DETECTIVE_BGM_DIR, filename)
    if not os.path.exists(file_path): return

    if vc.is_playing(): vc.stop()
    ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg")
    try:
        vc.play(discord.FFmpegPCMAudio(file_path, executable=ffmpeg_path if os.path.exists(ffmpeg_path) else "ffmpeg"))
    except: pass

class DetectiveGame:
    def __init__(self, cid, host, players):
        self.cid = cid
        self.host = host
        self.players = players
        self.detective = None
        self.criminals = {} # user_id -> {"place":, "crime":, "member":}
        self.occupied_places = {} # place_name -> user_id
        self.target_place = None
        self.target_member_id = None
        self.round = 1
        self.hints = [] # list of {"author":, "content":, "type":, "item":}
        # [🛠️ 추가] 매 게임 시작 시 DETECTIVE_MAP에서 무작위로 5개의 장소만 사용
        self.available_places = random.sample(list(DETECTIVE_MAP.keys()), min(5, len(DETECTIVE_MAP))) if DETECTIVE_MAP else []

class DetectiveJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=60.0)
        self.host = host
        self.players = [host]

    @discord.ui.button(label="🙋‍♂️ 참여하기", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        embed.description = f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n(최소 3명 이상 필요)"
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🚀 게임 시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 3:
            await interaction.response.send_message("최소 3명 이상의 참가자가 필요합니다!", ephemeral=True)
            return
        
        cid = interaction.channel_id
        if not DETECTIVE_MAP:
            await interaction.response.send_message("❌ 탐정 게임 데이터(장소.txt)가 로드되지 않았습니다.", ephemeral=True)
            return

        detective = random.choice(self.players)
        game = DetectiveGame(cid, self.host, self.players)
        game.detective = detective
        detective_games[cid] = game
        
        roles_text = f"🕵️ 탐정: **{detective.name}**\n🩸 나머지 {len(self.players)-1}명은 범죄자입니다."
        await interaction.response.edit_message(content=f"🔍 **[탐정 수사극]** 게임을 시작합니다!\n{roles_text}", embed=None, view=None)
        
        await play_detective_bgm(interaction, "snoop.mp3")
        await start_detective_round_1(interaction.channel, cid)
        self.stop()

@bot.command(name="탐정", aliases=["탐정게임"])
async def cmd_detective(ctx):
    if ctx.channel.id in detective_games:
        await ctx.send("❌ 이미 해당 채널에서 탐정 수사극이 진행 중입니다.")
        return
    
    try: await play_sound(ctx, "intro.mp3")
    except: pass
    


    embed = discord.Embed(title="🔍 (모집 중) 미니게임 [탐정 수사극]", color=0x2C3E50)
    embed.description = f"**현재 참가자:** {ctx.author.mention}\n(최소 3명 이상 필요)"
    embed.add_field(name="📜 게임 목표", value="탐정은 범죄자들이 숨은 장소와 범죄명을 맞혀야 합니다.\n범죄자들은 탐정이 자신들을 찾지 못하도록 교묘한 힌트를 제공하세요!", inline=False)
    
    view = DetectiveJoinView(ctx.author)
    await ctx.send(embed=embed, view=view)



async def start_detective_round_1(channel, cid):
    game = detective_games.get(cid)
    if not game: return
    
    await channel.send("🚩 **라운드 1: 범죄자 은신**\n범죄자들은 아래 버튼 중 하나를 클릭하여 은신할 장소와 범죄명을 등록하세요! (선착순)")
    view = DetectivePlacePickView(game)
    await channel.send("📍 **은신 가능한 장소 목록:**", view=view)

class DetectivePlacePickView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=300.0)
        self.game = game
        self.finished_ids = set()
        
        # [🛠️ 수정] 전체 맵 대신 게임 시작 시 뽑힌 5개의 장소만 버튼으로 생성
        for i, place in enumerate(self.game.available_places):
            row = i // 5
            btn = discord.ui.Button(label=place, style=discord.ButtonStyle.secondary, custom_id=f"dt_p_{place}", row=row)
            btn.callback = self.make_callback(place)
            self.add_item(btn)

    def make_callback(self, place):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id == self.game.detective.id:
                await interaction.response.send_message("탐정님은 범죄자가 은신할 때까지 기다려 주세요!", ephemeral=True)
                return
            if interaction.user.id in self.finished_ids:
                await interaction.response.send_message("이미 은신을 마쳤습니다.", ephemeral=True)
                return
            if place in self.game.occupied_places:
                await interaction.response.send_message("이미 다른 범죄자가 선점한 장소입니다!", ephemeral=True)
                return
            
            modal = DetectiveCrimeModal(self.game, place, self)
            await interaction.response.send_modal(modal)
        return callback

class DetectiveCrimeModal(discord.ui.Modal, title="🕵️ 범죄 보고 및 은신"):
    crime_name = discord.ui.TextInput(label="저지른 범죄명 (주관식)", placeholder="예: 보석 절도, 비밀 문서 탈취 등", min_length=2, max_length=20)
    
    def __init__(self, game, place, parent_view):
        super().__init__()
        self.game = game
        self.place = place
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        if self.place in self.game.occupied_places:
            await interaction.response.send_message("잠깐 사이 다른 범죄자가 이곳을 선점했습니다! 다른 곳을 골라주세요.", ephemeral=True)
            return
            
        self.game.occupied_places[self.place] = interaction.user.id
        self.game.criminals[interaction.user.id] = {"place": self.place, "crime": self.crime_name.value, "member": interaction.user}
        self.parent_view.finished_ids.add(interaction.user.id)
        
        await interaction.response.send_message(f"✅ **[{self.place}]** 장소에 은신했습니다. (범죄명: {self.crime_name.value})", ephemeral=True)
        
        if len(self.parent_view.finished_ids) == (len(self.game.players) - 1):
            channel = bot.get_channel(self.game.cid)
            await channel.send("📢 **모든 범죄자가 은신하고 범죄 계획을 마쳤습니다! 탐정의 수사가 시작됩니다.**")
            await start_detective_round_2(channel, self.game.cid)
            self.parent_view.stop()

async def start_detective_round_2(channel, cid):
    game = detective_games.get(cid)
    if not game: return
    
    await channel.send(f"🚩 **라운드 2: 탐정의 수사 현장 지목**\n{game.detective.mention} 탐정님, 범죄자들이 숨어 있는 것으로 의심되는 장소 중 하나를 골라 수사를 시작하세요!")
    view = DetectiveSiteSelectView(game)
    await channel.send("📍 **수사 의심 장소 (선택한 곳에 숨은 유저가 타겟이 됩니다):**", view=view)

class DetectiveSiteSelectView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=180.0)
        self.game = game
        
        options = [discord.SelectOption(label=p, value=p) for p in game.occupied_places.keys()]
        select = discord.ui.Select(placeholder="현장을 지목하세요 (탐정 전용)", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.detective.id:
            await interaction.response.send_message("탐정님만 수사 장소를 결정할 수 있습니다!", ephemeral=True)
            return
        
        place = interaction.data['values'][0]
        self.game.target_place = place
        self.game.target_member_id = self.game.occupied_places[place]
        
        await interaction.response.edit_message(content=f"🕵️ **[{place}]** 현장을 제보받았습니다! 이곳을 집중 수사합니다.", view=None)
        await start_detective_round_3(bot.get_channel(self.game.cid), self.game.cid)
        self.stop()

async def start_detective_round_3(channel, cid):
    game = detective_games.get(cid)
    if not game: return
    
    # 타겟 제외 나머지 범죄자 중 랜덤 2~3명 목격자 선정
    # [수정] 목격자 선정 로직 (3인 대응)
    criminals_ids = list(game.criminals.keys())
    if len(criminals_ids) == 2:
        others = criminals_ids
    else:
        others = [uid for uid in criminals_ids if uid != game.target_member_id]
    
    witness_count = min(len(others), random.randint(2, 3))
    witnesses = random.sample(others, witness_count)
    
    target_user = game.criminals[game.target_member_id]["member"]
    game.waiting_round_3 = witness_count
    
    view = DetectiveR3View(game, witnesses, target_user.display_name)
    await channel.send(f"🚩 **라운드 3: 인물 힌트 (익명 목격자 진술)**\n은밀한 목격자들이 지목되었습니다! (누가 지목되었는지는 비밀입니다)\n아래 버튼을 눌러 자신이 목격자인지 확인하고 힌트를 작성하세요!", view=view)

class DetectiveR3View(discord.ui.View):
    def __init__(self, game, witnesses, target_name):
        super().__init__(timeout=300.0)
        self.game = game
        self.witnesses = witnesses
        self.target_name = target_name
        self.submitted = set()

    @discord.ui.button(label="📝 인물 힌트 작성 (목격자 전용)", style=discord.ButtonStyle.primary)
    async def btn_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.witnesses:
            await interaction.response.send_message("❌ 당신은 이번 라운드 목격자가 아닙니다. 조용히 대기하세요!", ephemeral=True)
            return
        if interaction.user.id in self.submitted:
            await interaction.response.send_message("✅ 이미 진술을 마쳤습니다.", ephemeral=True)
            return
        crime_name = self.game.criminals[self.game.target_member_id]["crime"]
        modal = DetectiveHintModal(self.game, "인물", f"[{self.target_name}]의 외모/특징은?", custom_title=f"🕵️ 대상 범죄: {crime_name}")
        modal.view_ref = self
        await interaction.response.send_modal(modal)

class DetectiveR4View(discord.ui.View):
    def __init__(self, game, targets_map):
        super().__init__(timeout=300.0)
        self.game = game
        self.targets_map = targets_map
        self.submitted = set()

    @discord.ui.button(label="📝 수법 힌트 작성 (진술자 전용)", style=discord.ButtonStyle.danger)
    async def btn_submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.targets_map:
            await interaction.response.send_message("❌ 당신은 이번 라운드 진술자가 아닙니다.", ephemeral=True)
            return
        if interaction.user.id in self.submitted:
            await interaction.response.send_message("✅ 이미 진술을 마쳤습니다.", ephemeral=True)
            return
        item = self.targets_map[interaction.user.id]
        crime_name = self.game.criminals[self.game.target_member_id]["crime"]
        modal = DetectiveHintModal(self.game, "물건", f"물건 [{item}] 활용 수법은?", item=item, custom_title=f"🕵️ 대상 범죄: {crime_name}")
        modal.view_ref = self
        await interaction.response.send_modal(modal)

class DetectiveHintModal(discord.ui.Modal):
    content = discord.ui.TextInput(label="내용", style=discord.TextStyle.paragraph, min_length=2, max_length=50)
    
    def __init__(self, game, hint_type, label, item=None, custom_title="🕵️ 수사 힌트 제공"):
        super().__init__(title=custom_title[:45])
        self.game = game
        self.hint_type = hint_type
        self.item = item
        self.children[0].label = label

    async def on_submit(self, interaction: discord.Interaction):
        # 1. 3초 타임아웃 에러 방지를 위해 모달창을 가장 먼저 닫아줌 (응답)
        await interaction.response.send_message("✅ 힌트가 안전하게 전달되었습니다.", ephemeral=True)

        # 2. 데이터 저장 로직
        hint_data = {"author": interaction.user.name, "author_id": interaction.user.id, "content": self.content.value, "type": self.hint_type, "item": self.item}
        self.game.hints.append(hint_data)
        
        if hasattr(self, "view_ref"):
            self.view_ref.submitted.add(interaction.user.id)

        # 3. 채널 출력 및 다음 라운드 진행 로직
        channel = bot.get_channel(self.game.cid)
        if self.hint_type == "인물":
            await channel.send(f"👤 **익명의 목격자:** {self.content.value}")
            if hasattr(self.game, "waiting_round_3"):
                self.game.waiting_round_3 -= 1
                if getattr(self.game, "waiting_round_3", 1) <= 0:
                    delattr(self.game, "waiting_round_3")
                    await asyncio.sleep(2)
                    await start_detective_round_4(channel, self.game.cid)
        else:
            await channel.send(f"🩸 **물건 [{self.item}] 관련 진술:** {self.content.value}")
            if hasattr(self.game, "waiting_round_4"):
                self.game.waiting_round_4 -= 1
                if getattr(self.game, "waiting_round_4", 1) <= 0:
                    delattr(self.game, "waiting_round_4")
                    await asyncio.sleep(2)
                    await start_detective_round_5(channel, self.game.cid)

async def start_detective_round_4(channel, cid):
    game = detective_games.get(cid)
    if not game: return
    
    await channel.send(f"🚩 **라운드 4: 범행 수법 힌트 (물건 추리)**\n{game.detective.mention} 탐정님, 현장에서 발견된 물건 중 의심스러운 **2개**를 골라 자세한 진술을 요구하세요!")
    
    words = DETECTIVE_MAP.get(game.target_place, [])
    sample_words = random.sample(words, min(len(words), 4))
    
    view = DetectiveItemSelectView(game, sample_words)
    await channel.send("📦 **현장 유류물 리스트 (2개 선택):**", view=view)

class DetectiveItemSelectView(discord.ui.View):
    def __init__(self, game, items):
        super().__init__(timeout=180.0)
        self.game = game
        options = [discord.SelectOption(label=item, value=item) for item in items]
        select = discord.ui.Select(placeholder="의심 물건 2개를 고르세요", options=options, min_values=2, max_values=2)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.detective.id:
            await interaction.response.send_message("탐정님만 물건을 고를 수 있습니다!", ephemeral=True)
            return
        
        selected_items = interaction.data['values']
        await interaction.response.edit_message(content=f"🔍 **[{', '.join(selected_items)}]** 물건들에 대해 정밀 감식을 요청했습니다.", view=None)
        
        # [수정] 목격자 선정 로직 (3인 대응)
        criminals_ids = list(self.game.criminals.keys())
        if len(criminals_ids) == 2:
            others = criminals_ids
        else:
            others = [uid for uid in criminals_ids if uid != self.game.target_member_id]
            
        targets = random.sample(others, min(len(others), 2))
        
        self.game.waiting_round_4 = len(targets)
        targets_map = {targets[i]: selected_items[i % len(selected_items)] for i in range(len(targets))}
        
        channel = bot.get_channel(self.game.cid)
        view = DetectiveR4View(self.game, targets_map)
        await channel.send("📦 **지목된 물건들에 대한 진술자를 선정했습니다!**\n자신이 진술자인지 아래 버튼을 눌러 확인하고 힌트를 제출하세요.", view=view)
        self.stop()

async def start_detective_round_5(channel, cid):
    game = detective_games.get(cid)
    if not game: return
    
    await channel.send(f"🚩 **마지막 라운드: 탐정의 최종 판결**\n{game.detective.mention} 탐정님, 이제 모든 증거가 수집되었습니다. 범죄자와 그가 저지른 범죄명을 지목하세요!")
    
    crimes = [c["crime"] for c in game.criminals.values()]
    view = DetectiveFinalJudgmentView(game, crimes)
    await channel.send("⚖️ **최종 판단 (용의자 및 범죄명 선택):**", view=view)

class DetectiveFinalJudgmentView(discord.ui.View):
    def __init__(self, game, crimes):
        super().__init__(timeout=300.0)
        self.game = game
        self.selected_suspect = None
        self.selected_crime = None
        
        # 용의자 목록
        sus_options = [discord.SelectOption(label=c["member"].display_name, value=str(uid)) for uid, c in game.criminals.items()]
        sus_select = discord.ui.Select(placeholder="용의자(범죄자 유저) 선택", options=sus_options, custom_id="dt_final_sus")
        sus_select.callback = self.suspect_callback
        self.add_item(sus_select)
        
        # 범죄명 목록 (셔플)
        random.shuffle(crimes)
        crime_options = [discord.SelectOption(label=c, value=f"{i}_{c}") for i, c in enumerate(crimes)]
        crime_select = discord.ui.Select(placeholder="범죄명 선택", options=crime_options, custom_id="dt_final_crime")
        crime_select.callback = self.crime_callback
        self.add_item(crime_select)

    async def suspect_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.detective.id: return
        self.selected_suspect = int(interaction.data['values'][0])
        await interaction.response.defer()
        await self.check_ready(interaction)

    async def crime_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.detective.id: return
        self.selected_crime = interaction.data['values'][0].split('_', 1)[1]
        await interaction.response.defer()
        await self.check_ready(interaction)

    async def check_ready(self, interaction):
        if self.selected_suspect and self.selected_crime:
            is_correct_user = (self.selected_suspect == self.game.target_member_id)
            is_correct_crime = (self.selected_crime == self.game.criminals[self.game.target_member_id]["crime"])
            
            channel = bot.get_channel(self.game.cid)
            target_user = self.game.criminals[self.game.target_member_id]["member"]
            real_crime = self.game.criminals[self.game.target_member_id]["crime"]
            
            # [추가] 탐정이 지목했던 헛다리(또는 정답) 정보 추출
            guessed_user = self.game.criminals[self.selected_suspect]["member"]
            guessed_crime = self.selected_crime
            
            if is_correct_user and is_correct_crime:
                embed = discord.Embed(title="🎊 탐정 수사 승리!", color=0x2ECC71)
                embed.description = f"탐정 {self.game.detective.mention}님이 완벽하게 추리해냈습니다!\n\n🕵️ **탐정의 지목:** {guessed_user.mention} ({guessed_crime})\n📍 **현장:** {self.game.target_place}\n👤 **범죄자:** {target_user.mention}\n🗡️ **범죄명:** {real_crime}"
                await channel.send(embed=embed)
                del detective_games[self.game.cid]
            else:
                embed = discord.Embed(title="❌ 탐정 수사 실패 (범죄자 팀 승리)", color=0xE74C3C)
                embed.description = f"탐정의 판결이 빗나갔습니다. 범죄자들이 유유히 현장을 빠져나갑니다!\n\n🕵️ **탐정의 지목 (헛다리):** {guessed_user.mention} ({guessed_crime})\n\n📍 **현장:** {self.game.target_place}\n👤 **진짜 범죄자:** {target_user.mention}\n🗡️ **진짜 범죄명:** {real_crime}"
                await channel.send(embed=embed)
                # 패배 시 보너스 투표
                await start_detective_bonus(channel, self.game)
            
            # 기존에 interaction.message.edit(view=None) 처리가 있다면 유지, 없다면 패스 (UI 닫기 처리용)
            try:
                await interaction.message.edit(view=None)
            except:
                pass
                
            self.stop()

async def start_detective_bonus(channel, game):
    await channel.send("🗳️ **[보너스: 워스트/베스트 힌트 투표]**\n탐정님, 수사를 방해한 트롤러와 가장 도움된 목격자를 지목해 주세요.")
    
    view = DetectiveBonusView(game)
    await channel.send("💩 **먼저, 수사에 가장 방해된 '워스트 힌트'를 골라주세요:**", view=view)

class DetectiveBonusView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=300.0)
        self.game = game
        self.step = 1 # 1: Worst, 2: Best
        
        options = [discord.SelectOption(label=f"[{h['type']}] {h['content'][:30]}...", value=str(i)) for i, h in enumerate(game.hints)]
        options.append(discord.SelectOption(label="[없음] 모든 힌트가 무난했습니다.", value="-1"))
        
        self.select = discord.ui.Select(placeholder="힌트를 선택하세요", options=options, custom_id="dt_bonus_sel")
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.detective.id: return
        idx = int(interaction.data['values'][0])

        if self.step == 1:
            await play_detective_bgm(interaction, "down.mp3")
            if idx == -1:
                await interaction.channel.send("🕊️ 평화주의 탐정님! 워스트 힌트를 고르지 않으셨습니다.")
            else:
                hint = self.game.hints[idx]
                await interaction.channel.send(f"💩 **워스트 힌트 공개:** 작성자 **[{hint['author']}]**\n\"{hint['content']}\" (트롤 처리)")

            self.step = 2
            self.clear_items() # 기존 드롭다운을 삭제하고 완전히 새로 만들어서 초기화
            options = [discord.SelectOption(label=f"[{h['type']}] {h['content'][:30]}...", value=str(i)) for i, h in enumerate(self.game.hints)]
            options.append(discord.SelectOption(label="[없음] 모두 무난했습니다.", value="-1"))
            new_select = discord.ui.Select(placeholder="가장 도움된 '베스트 힌트'를 골라주세요", options=options, custom_id="dt_bonus_best")
            new_select.callback = self.on_select
            self.add_item(new_select)

            await interaction.response.edit_message(content="🌟 **이제 수사에 가장 도움된 '베스트 힌트'를 골라주세요:**", view=self)
        else:
            await play_detective_bgm(interaction, "carry.mp3")
            if idx == -1:
                await interaction.channel.send("베스트가 마땅히 없으셨군요. 게임을 종료합니다.")
            else:
                hint = self.game.hints[idx]
                await interaction.channel.send(f"🌟 **베스트 힌트 공개:** 작성자 **[{hint['author']}]**\n\"{hint['content']}\" (명예 점수 2배!)")

            if self.game.cid in detective_games: del detective_games[self.game.cid]
            await interaction.response.edit_message(content="✅ **보너스 투표가 종료되었습니다.**", view=None)
            self.stop()

# ==========================================
# 🕵️ [추적 탐정] 게임 로직 (Track Detective)
# ==========================================

class TrackGame:
    def __init__(self, cid, host, players):
        self.cid = cid
        self.host = host
        self.players = players
        self.detective = None
        self.criminals = {} # {id: {"member": member, "path": [], "crime": ""}}
        self.remaining_criminals = [] # 아직 잡히지 않은 범죄자 (Member 객체)
        self.caught_criminals = [] # 검거된 범죄자 (Member 객체)
        self.current_suspects = []
        self.locked_target = None
        self.submitted_criminals = set()
        self.final_places = {} # {place: member_id}
        self.hints = []
        # [🛠️ 변경] 매 게임 시작 시 TRACK_MAP에서 무작위로 10개의 장소만 사용
        self.available_places = random.sample(TRACK_MAP, min(10, len(TRACK_MAP))) if TRACK_MAP else []

class TrackJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=60.0)
        self.host = host
        self.players = [host]

    @discord.ui.button(label="🙋‍♂️ 참여하기", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("이미 참여 중입니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        embed.description = f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n(최소 3명 필요)"
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🚀 게임시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 3:
            await interaction.response.send_message("최소 3명 이상의 참가자가 필요합니다!", ephemeral=True)
            return

        cid = interaction.channel_id
        if cid in track_games:
            await interaction.response.send_message("❌ 이미 진행 중인 게임이 있습니다.", ephemeral=True)
            return

        game = TrackGame(cid, self.host, self.players)
        track_games[cid] = game
        
        # 역할 분담
        game.detective = random.choice(game.players)
        criminals_list = [p for p in game.players if p.id != game.detective.id]
        game.remaining_criminals = criminals_list.copy()
        for c in criminals_list:
            game.criminals[c.id] = {"member": c, "path": [], "crime": ""}

        await interaction.response.edit_message(content="🎭 **[추적 탐정] 게임을 시작합니다!**", embed=None, view=None)
        try: await play_detective_bgm(interaction, "snoop.mp3")
        except: pass
        
        # 라운드 1 시작: 범죄자 경로 계획
        embed = discord.Embed(title="🕵️ [추적 탐정] 라운드 1: 도주 경로 계획", color=0x3498DB)
        embed.description = f"탐정: {game.detective.mention}\n범죄자들은 자신의 도주 경로(1차, 2차, 최종)를 계획하세요.\n\n**[주의]** 최종 은신 장소는 다른 범죄자와 겹칠 수 없습니다."
        await interaction.channel.send(embed=embed)
        
        # 범죄자들에게 개인 메시지 또는 버튼 제공
        view = TrackPathStartView(game)
        await interaction.channel.send("📍 범죄자들은 아래 버튼을 눌러 경로를 설정해 주세요.", view=view)

class TrackPathStartView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=300.0)
        self.game = game

    @discord.ui.button(label="📍 경로 및 범죄 설정", style=discord.ButtonStyle.grey)
    async def set_path(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.criminals:
            await interaction.response.send_message("범죄자만 참여할 수 있습니다.", ephemeral=True)
            return
        
        view = TrackPathSelectView(self.game, interaction.user)
        await interaction.response.send_message("도주 경로 3곳을 선택하세요.", view=view, ephemeral=True)

class TrackPathSelectView(discord.ui.View):
    def __init__(self, game, member):
        super().__init__(timeout=300.0)
        self.game = game
        self.member = member
        self.p1 = None
        self.p2 = None
        self.pf = None

        # [🛠️ 변경] 전체 맵 대신 게임 시작 시 뽑힌 10개의 장소만 사용
        options = [discord.SelectOption(label=place, value=place) for place in self.game.available_places]
        
        s1 = discord.ui.Select(placeholder="1차 장소 선택", options=options, custom_id="p1")
        s1.callback = self.s1_cb
        self.add_item(s1)
        
        s2 = discord.ui.Select(placeholder="2차 장소 선택", options=options, custom_id="p2")
        s2.callback = self.s2_cb
        self.add_item(s2)
        
        sf = discord.ui.Select(placeholder="최종 장소 선택", options=options, custom_id="pf")
        sf.callback = self.sf_cb
        self.add_item(sf)

    async def s1_cb(self, interaction): self.p1 = interaction.data['values'][0]; await interaction.response.defer()
    async def s2_cb(self, interaction): self.p2 = interaction.data['values'][0]; await interaction.response.defer()
    async def sf_cb(self, interaction): self.pf = interaction.data['values'][0]; await interaction.response.defer()

    @discord.ui.button(label="✅ 경로 확정 및 범죄명 작성", style=discord.ButtonStyle.green, row=3)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not all([self.p1, self.p2, self.pf]):
            await interaction.response.send_message("3개의 장소를 모두 선택해야 합니다!", ephemeral=True)
            return
        
        # 최종 장소 중복 체크
        if self.pf in self.game.final_places and self.game.final_places[self.pf] != self.member.id:
            await interaction.response.send_message("❌ 이미 다른 범죄자가 선택한 최종 장소입니다. 다른 곳을 골라주세요.", ephemeral=True)
            return

        modal = TrackCrimeModal(self.game, self.member, [self.p1, self.p2, self.pf])
        await interaction.response.send_modal(modal)

class TrackCrimeModal(discord.ui.Modal, title="범죄명 작성"):
    crime_input = discord.ui.TextInput(label="당신의 범죄명 (진짜)", placeholder="예: 보석 탈취, 은행 강도 등", min_length=2, max_length=20)
    fake_crime_input = discord.ui.TextInput(label="가짜 범죄명 (탐정 교란용)", placeholder="탐정을 속일 가짜 범죄명", min_length=2, max_length=20)

    def __init__(self, game, member, path):
        super().__init__()
        self.game = game
        self.member = member
        self.path = path

    async def on_submit(self, interaction: discord.Interaction):
        pf = self.path[2]
        if pf in self.game.final_places and self.game.final_places[pf] != self.member.id:
            await interaction.response.send_message("❌ 그 사이 다른 범죄자가 최종 장소를 선점했습니다. 다시 시도해 주세요.", ephemeral=True)
            return

        self.game.criminals[self.member.id]["path"] = self.path
        self.game.criminals[self.member.id]["crime"] = self.crime_input.value
        self.game.criminals[self.member.id]["fake_crime"] = self.fake_crime_input.value
        self.game.final_places[pf] = self.member.id
        self.game.submitted_criminals.add(self.member.id)
        
        await interaction.response.send_message(f"✅ 경로와 범죄명이 등록되었습니다!\n1차: {self.path[0]} -> 2차: {self.path[1]} -> 최종: {self.path[2]}\n진짜 범죄: {self.crime_input.value} / 가짜 범죄: {self.fake_crime_input.value}", ephemeral=True)
        
        if len(self.game.submitted_criminals) == len(self.game.criminals):
            await start_track_round2(self.game)

async def start_track_round2(game):
    if game.cid not in track_games: return
    channel = bot.get_channel(game.cid)
    
    # 데이터 초기화 (새로운 타겟 추적 준비)
    game.hints = []
    game.locked_target = None
    game.current_suspects = []

    await channel.send("📢 **수사망을 좁힙니다.**\n\n라운드 2: 탐정의 1차 장소 지목이 시작됩니다.")
    
    # 아직 잡히지 않은 범죄자들이 실제로 출발한 1차 장소들 (중복 제거)
    remaining_ids = [m.id for m in game.remaining_criminals]
    start_places = list(set([c["path"][0] for rid, c in game.criminals.items() if rid in remaining_ids]))
    
    view = TrackRound2View(game, start_places)
    await channel.send(f"🕵️ {game.detective.mention} 탐정님, 남은 범죄자들이 나타난 **1차 장소** 중 한 곳을 수사하세요.", view=view)

class TrackRound2View(discord.ui.View):
    def __init__(self, game, start_places):
        super().__init__(timeout=180.0)
        self.game = game
        options = [discord.SelectOption(label=p, value=p) for p in start_places]
        select = discord.ui.Select(placeholder="수사할 1차 장소 선택", options=options)
        select.callback = self.callback
        self.add_item(select)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.detective.id:
            await interaction.response.send_message("탐정만 선택할 수 있습니다.", ephemeral=True)
            return
        
        place = interaction.data['values'][0]
        self.game.current_suspects = [c["member"] for c in self.game.criminals.values() if c["path"][0] == place]
        
        await interaction.response.edit_message(content=f"📍 탐정이 **{place}**를 수사합니다!\n발견된 용의자: {', '.join([p.mention for p in self.game.current_suspects])}", view=None)
        await start_track_round3(self.game)

async def start_track_round3(game):
    if game.cid not in track_games: return
    channel = bot.get_channel(game.cid)
    
    staters = game.current_suspects
    if len(staters) > 1:
        await channel.send("📢 **라운드 3: 1차 수집 (범죄명 & 2차 장소 힌트)**\n⚠️ **[현장 겹침 발생!]** 여러 명의 용의자가 한 장소에서 발견되었습니다.\n용의자 전원이 각자의 범죄명을 진술하고, 목격자들은 이들의 2차 장소를 무작위로 섞어서 진술합니다!")
    else:
        await channel.send("📢 **라운드 3: 1차 수집 (범죄명 & 2차 장소 힌트)**\n용의자는 자신의 범죄명을, 다른 범죄자들은 용의자의 도주 경로를 진술합니다.")
    
    # [수정] 범죄자 3인 이상일 때 '전원 목격자' 시스템 적용
    all_criminals = [c["member"] for c in game.criminals.values()]
    # 진술자(staters)를 제외한 모든 범죄자가 목격자가 됨
    witnesses = [c for c in all_criminals if c.id not in [s.id for s in staters]]
    
    # 만약 모든 범죄자가 1차 장소에 모여있어 목격자가 없다면, 전원을 목격자로 지정
    if not witnesses:
        witnesses = all_criminals
    
    view = TrackRound3View(game, staters, witnesses)
    await channel.send("아래 버튼을 눌러 힌트를 작성해 주세요. (모든 힌트는 익명으로 채널에 출력됩니다)", view=view)

class TrackRound3View(discord.ui.View):
    def __init__(self, game, staters, witnesses):
        super().__init__(timeout=300.0)
        self.game = game
        self.staters = staters if isinstance(staters, list) else [staters]
        self.witnesses = witnesses
        self.submitted = set()
        self.expected_hints = len(self.staters) + len(self.witnesses)

    @discord.ui.button(label="📝 범죄명 진술 (진술자 전용)", style=discord.ButtonStyle.primary)
    async def state_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [s.id for s in self.staters]:
            await interaction.response.send_message("당신은 진술자가 아닙니다.", ephemeral=True)
            return
            
        my_crime = self.game.criminals[interaction.user.id]["crime"]
        label_txt = f"내 범죄 [{my_crime}] 힌트 작성"
        modal = TrackHintModal(self.game, "범죄명 힌트", label_txt, view_ref=self, round_num=3)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="👁️ 경로 목격 진술 (목격자 전용)", style=discord.ButtonStyle.secondary)
    async def witness_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [w.id for w in self.witnesses]:
            await interaction.response.send_message("당신은 선정된 목격자가 아닙니다.", ephemeral=True)
            return
            
        places = list(set([self.game.criminals[s.id]["path"][1] for s in self.staters]))
        if len(self.staters) > 1:
            label_txt = f"[{', '.join(places)}] 중 하나 골라 작성"
        else:
            label_txt = f"도주 경로 [{places[0]}] 힌트 작성"
        modal = TrackHintModal(self.game, "2차 장소 힌트", label_txt, view_ref=self, round_num=3)
        await interaction.response.send_modal(modal)

class TrackHintModal(discord.ui.Modal):
    hint_input = discord.ui.TextInput(label="힌트 내용", style=discord.TextStyle.paragraph, min_length=2, max_length=100)

    def __init__(self, game, title, label, view_ref=None, round_num=None):
        super().__init__(title=title[:45])
        self.game = game
        self.hint_input.label = label[:45]
        self.view_ref = view_ref
        self.round_num = round_num

    async def on_submit(self, interaction: discord.Interaction):
        hint_data = {
            "author": interaction.user.name,
            "content": self.hint_input.value,
            "type": self.title
        }
        self.game.hints.append(hint_data)

        channel = bot.get_channel(self.game.cid)
        embed = discord.Embed(title=f"📩 익명 힌트 도착 ({self.title})", description=f"\"{self.hint_input.value}\"", color=0x95A5A6)
        await channel.send(embed=embed)
        await interaction.response.send_message("힌트가 제출되었습니다.", ephemeral=True)
        
        # [자동화 로직] 힌트가 목표 개수에 도달하면 자동으로 다음 라운드 진행
        if self.view_ref:
            self.view_ref.submitted.add(f"{interaction.user.id}_{self.title}")
            if len(self.view_ref.submitted) >= self.view_ref.expected_hints:
                self.view_ref.stop()
                if self.round_num == 3:
                    await channel.send("✅ **모든 힌트 수집이 완료되었습니다! 다음 라운드로 이동합니다.**")
                    await asyncio.sleep(2)
                    await start_track_round4(self.game)
                elif self.round_num == 5:
                    await channel.send("✅ **모든 힌트 수집이 완료되었습니다! 최종 판결로 이동합니다.**")
                    await asyncio.sleep(2)
                    await start_track_round6(self.game)

async def start_track_round4(game):
    if game.cid not in track_games: return
    channel = bot.get_channel(game.cid)
    await channel.send("📢 **라운드 4: 탐정의 2차 장소 추적**\n탐정은 용의자들이 이동했을 법한 2차 장소를 지목합니다.")
    
    # 1차 장소 제외 뽑힌 10개 장소 중 선택
    p1_place = game.criminals[game.current_suspects[0].id]["path"][0]
    options_places = [p for p in game.available_places if p != p1_place]
    
    view = TrackRound4View(game, options_places)
    await channel.send(f"🕵️ {game.detective.mention} 탐정님, 용의자들이 이동한 **2차 장소**를 하나 고르세요.", view=view)

class TrackRound4View(discord.ui.View):
    def __init__(self, game, places):
        super().__init__(timeout=180.0)
        self.game = game
        options = [discord.SelectOption(label=p, value=p) for p in places]
        select = discord.ui.Select(placeholder="추적할 2차 장소 선택", options=options)
        select.callback = self.callback
        self.add_item(select)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.detective.id:
            await interaction.response.send_message("탐정만 선택할 수 있습니다.", ephemeral=True)
            return
        
        target_place = interaction.data['values'][0]
        matches = [s for s in self.game.current_suspects if self.game.criminals[s.id]["path"][1] == target_place]
        
        if not matches:
            await interaction.response.edit_message(content=f"❌ **수사망 돌파!**\n탐정이 **{target_place}**를 지목했으나 아무도 없었습니다. 범죄자 한 명을 놓치면서 모든 수사가 수포로 돌아갔습니다.\n**탐정 패배 (범죄자 팀 승리)**", view=None)
            
            # [수정] 조기 패배 시에도 워스트/베스트 보너스 투표 호출! (down.mp3 재생을 위해)
            channel = bot.get_channel(self.game.cid)
            await start_track_bonus(channel, self.game)
            return
        
        self.game.locked_target = random.choice(matches)
        await interaction.response.edit_message(content=f"🎯 추적 성공! 탐정이 **{target_place}**에서 용의자의 흔적을 발견했습니다.\n이제 최종 타겟을 압박합니다.", view=None)
        await start_track_round5(self.game)

async def start_track_round5(game):
    if game.cid not in track_games: return
    channel = bot.get_channel(game.cid)
    await channel.send(f"📢 **라운드 5: 2차 수집 (최종 장소 힌트)**\n타겟 {game.locked_target.mention}은 자신의 범죄에 대한 추가 힌트를, 목격자들은 최종 은신처에 대한 힌트를 줍니다.")
    
    # [수정] 타겟을 제외한 모든 범죄자를 목격자로 선정
    all_criminals = [c["member"] for c in game.criminals.values()]
    witnesses = [c for c in all_criminals if c.id != game.locked_target.id]
    
    view = TrackRound5View(game, witnesses)
    await channel.send("아래 버튼을 눌러 힌트를 작성해 주세요.", view=view)

class TrackRound5View(discord.ui.View):
    def __init__(self, game, witnesses):
        super().__init__(timeout=300.0)
        self.game = game
        self.witnesses = witnesses
        self.submitted = set()
        self.expected_hints = 1 + len(self.witnesses)

    @discord.ui.button(label="📝 추가 범죄 힌트 (타겟 전용)", style=discord.ButtonStyle.primary)
    async def target_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.locked_target.id:
            await interaction.response.send_message("당신은 타겟이 아닙니다.", ephemeral=True)
            return
            
        my_crime = self.game.criminals[interaction.user.id]["crime"]
        label_txt = f"내 범죄 [{my_crime}] 추가 힌트 작성"
        modal = TrackHintModal(self.game, "추가 범죄 힌트", label_txt, view_ref=self, round_num=5)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="👁️ 최종 은신처 목격 진술", style=discord.ButtonStyle.secondary)
    async def witness_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [w.id for w in self.witnesses]:
            await interaction.response.send_message("당신은 선정된 목격자가 아닙니다.", ephemeral=True)
            return
            
        final_place = self.game.criminals[self.game.locked_target.id]["path"][2]
        label_txt = f"최종 은신처 [{final_place}] 힌트 작성"
        modal = TrackHintModal(self.game, "최종 장소 힌트", label_txt, view_ref=self, round_num=5)
        await interaction.response.send_modal(modal)

async def start_track_round6(game):
    if game.cid not in track_games: return
    channel = bot.get_channel(game.cid)
    await channel.send("📢 **라운드 6: 최종 판결**\n탐정은 타겟의 **최종 은신 장소**와 **범죄명**을 정확히 맞혀야 합니다.")
    
    all_crimes = [c["crime"] for c in game.criminals.values()]
    random.shuffle(all_crimes)
    
    view = TrackRound6View(game, all_crimes)
    await channel.send(f"🕵️ {game.detective.mention} 탐정님, 최종 판결을 내려주세요.", view=view)

class TrackRound6View(discord.ui.View):
    def __init__(self, game, crimes):
        super().__init__(timeout=300.0)
        self.game = game
        self.sel_place = None
        self.sel_crime = None

        # [🛠️ 변경] 전체 맵 대신 게임 시작 시 뽑힌 10개의 장소만 사용
        p_options = [discord.SelectOption(label=p, value=p) for p in self.game.available_places]
        ps = discord.ui.Select(placeholder="최종 장소 지목", options=p_options)
        ps.callback = self.p_cb
        self.add_item(ps)
        
        c_options = [discord.SelectOption(label=c, value=c) for c in crimes[:25]]
        cs = discord.ui.Select(placeholder="범죄명 지목", options=c_options)
        cs.callback = self.c_cb
        self.add_item(cs)

    async def p_cb(self, interaction): self.sel_place = interaction.data['values'][0]; await interaction.response.defer()
    async def c_cb(self, interaction): self.sel_crime = interaction.data['values'][0]; await interaction.response.defer()

    @discord.ui.button(label="⚖️ 최종 판결 확정", style=discord.ButtonStyle.danger, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not all([self.sel_place, self.sel_crime]):
            await interaction.response.send_message("장소와 범죄명을 모두 선택해야 합니다!", ephemeral=True)
            return
        
        target_info = self.game.criminals[self.game.locked_target.id]
        is_win = (self.sel_place == target_info["path"][2]) and (self.sel_crime == target_info["crime"])
        
        channel = bot.get_channel(self.game.cid)
        if is_win:
            # 검거 처리
            captured = self.game.locked_target
            self.game.caught_criminals.append(captured)
            self.game.remaining_criminals = [m for m in self.game.remaining_criminals if m.id != captured.id]

            if self.game.remaining_criminals:
                embed = discord.Embed(title="🎯 검거 성공!", color=0x2ECC71)
                embed.description = f"탐정 {self.game.detective.mention}님이 타겟 {captured.mention}을 검거했습니다!\n하지만 아직 공범이 남아있습니다. 다음 추적을 시작합니다."
                await channel.send(embed=embed)
                await interaction.response.edit_message(view=None)
                await start_track_round2(self.game)
            else:
                try: await play_sound(await bot.get_context(interaction.message), "carry.mp3")
                except: pass
                embed = discord.Embed(title="🎊 [추적 탐정] 모든 범죄자 검거 완료!", color=0x2ECC71)
                embed.description = f"탐정 {self.game.detective.mention}님이 모든 범죄자를 소탕했습니다! 완벽한 승리입니다!\n\n👤 **마지막 타겟:** {captured.mention}\n📍 **최종 장소:** {target_info['path'][2]}\n🗡️ **범죄명:** {target_info['crime']}"
                await channel.send(embed=embed)
                await interaction.response.edit_message(view=None)
                if self.game.cid in track_games: del track_games[self.game.cid]
        else:
            embed = discord.Embed(title="❌ 수사망 돌파! (범죄자 팀 승리)", color=0xE74C3C)
            embed.description = f"탐정이 범죄자 중 한 명을 놓치면서 모든 수사가 수포로 돌아갔습니다!\n\n🕵️ **탐정의 오판:** {self.sel_place} ({self.sel_crime})\n\n👤 **진짜 타겟:** {self.game.locked_target.mention}\n📍 **진짜 장소:** {target_info['path'][2]}\n🗡️ **진짜 범죄명:** {target_info['crime']}"
            await channel.send(embed=embed)
            await interaction.response.edit_message(view=None)
            
            # [추가] 패배 시 보너스 투표 진행 (여기서는 게임 데이터를 지우지 않음)
            await start_track_bonus(channel, self.game)
        
        self.stop()

async def start_track_bonus(channel, game):
    await channel.send("🗳️ **[보너스: 워스트/베스트 힌트 투표]**\n탐정님, 수사를 방해한 트롤러와 가장 도움된 목격자를 지목해 주세요.")
    view = TrackBonusView(game)
    await channel.send("💩 **먼저, 수사에 가장 방해된 '워스트 힌트'를 골라주세요:**", view=view)

class TrackBonusView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=300.0)
        self.game = game
        self.step = 1 # 1: Worst, 2: Best
        
        options = [discord.SelectOption(label=f"[{h['type'][:10]}] {h['content'][:30]}...", value=str(i)) for i, h in enumerate(game.hints)]
        if not options:
            options.append(discord.SelectOption(label="제출된 힌트가 없습니다.", value="-1"))
        else:
            options.append(discord.SelectOption(label="[없음] 모든 힌트가 무난했습니다.", value="-1"))
            
        self.select = discord.ui.Select(placeholder="힌트를 선택하세요", options=options, custom_id="trk_bonus_sel")
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.detective.id: return
        idx = int(interaction.data['values'][0])

        if self.step == 1:
            try: await play_detective_bgm(interaction, "down.mp3")
            except: pass
            
            if idx == -1:
                await interaction.channel.send("🕊️ 평화주의 탐정님! 워스트 힌트를 고르지 않으셨습니다.")
            else:
                hint = self.game.hints[idx]
                await interaction.channel.send(f"💩 **워스트 힌트 공개:** 작성자 **[{hint['author']}]**\n\"{hint['content']}\" (트롤 처리)")

            self.step = 2
            self.clear_items()
            options = [discord.SelectOption(label=f"[{h['type'][:10]}] {h['content'][:30]}...", value=str(i)) for i, h in enumerate(self.game.hints)]
            if not options:
                options.append(discord.SelectOption(label="제출된 힌트가 없습니다.", value="-1"))
            else:
                options.append(discord.SelectOption(label="[없음] 모두 무난했습니다.", value="-1"))
                
            new_select = discord.ui.Select(placeholder="가장 도움된 '베스트 힌트'를 골라주세요", options=options, custom_id="trk_bonus_best")
            new_select.callback = self.on_select
            self.add_item(new_select)

            await interaction.response.edit_message(content="🌟 **이제 수사에 가장 도움된 '베스트 힌트'를 골라주세요:**", view=self)
        else:
            try: await play_detective_bgm(interaction, "carry.mp3")
            except: pass
            
            if idx == -1:
                await interaction.channel.send("베스트가 마땅히 없으셨군요. 게임을 종료합니다.")
            else:
                hint = self.game.hints[idx]
                await interaction.channel.send(f"🌟 **베스트 힌트 공개:** 작성자 **[{hint['author']}]**\n\"{hint['content']}\" (명예 점수 2배!)")

            if self.game.cid in track_games: del track_games[self.game.cid]
            await interaction.response.edit_message(content="✅ **보너스 투표가 종료되었습니다.**", view=None)
            self.stop()

@bot.command(name="추적")
async def cmd_track(ctx):
    if ctx.channel.id in track_games:
        await ctx.send("❌ 이미 이 채널에서 추적 탐정 게임이 진행 중입니다.")
        return
    try: await play_sound(ctx, "intro.mp3")
    except: pass
    view = TrackJoinView(ctx.author)
    embed = discord.Embed(title="📢 [추적 탐정] 게임 모집", description=f"**현재 참가자:** {ctx.author.mention}\n(최소 3명 필요)", color=0x3498DB)
    await ctx.send(embed=embed, view=view)

@bot.command(name="추적종료")
async def cmd_stop_track(ctx):
    cid = ctx.channel.id
    if cid in track_games:
        del track_games[cid]
        await stop_sound(ctx)
        await ctx.send("🛑 추적 탐정 게임을 강제 종료했습니다.")
    else:
        await ctx.send("❌ 현재 진행 중인 추적 탐정 게임이 없습니다.")


# ==========================================
# 🚇 [지하철 심리 추격전] (Subway Psychology Pursuit)
# ==========================================

SUBWAY_GRAPH = {
    "오이도역": {"하늘선": ["정왕역"]},
    "정왕역": {"하늘선": ["오이도역", "안산역"]},
    "안산역": {"하늘선": ["정왕역", "중앙역"]},
    "중앙역": {"하늘선": ["안산역", "상록수역"], "빨간선": ["월곶역"]},
    "상록수역": {"하늘선": ["중앙역", "금정역"]},
    "금정역": {"하늘선": ["상록수역", "과천역"]},
    "과천역": {"하늘선": ["금정역", "사당역"]},
    "사당역": {"하늘선": ["과천역", "용산역"], "초록선": ["강남역", "신도림역"]},
    "용산역": {"하늘선": ["사당역", "서울역"], "분홍선": ["충무로역", "고속터미널역"]}, 
    "서울역": {"하늘선": ["용산역", "동대문역"], "노란선": ["을지로역", "잠실역"], "초록선": ["시청역", "성수역"]},
    "동대문역": {"하늘선": ["서울역", "성신여대역"]},
    "성신여대역": {"하늘선": ["동대문역", "길음역"], "보라선": ["의정부역", "동묘앞역"]},
    "길음역": {"하늘선": ["성신여대역", "창동역"]},
    "창동역": {"하늘선": ["길음역", "노원역"], "회색선": ["청량리역"]},
    "노원역": {"하늘선": ["창동역", "당고개역"]},
    "당고개역": {"하늘선": ["노원역"]},
    "신촌역": {"초록선": ["시청역", "합정역"], "보라선": ["까치산역", "종로3가역"]},
    "시청역": {"초록선": ["서울역", "신촌역"], "분홍선": ["충무로역"]},
    "성수역": {"초록선": ["잠실역", "서울역"]},
    "잠실역": {"초록선": ["종합운동장역", "성수역"], "노란선": ["서울역", "도곡역"]},
    "종합운동장역": {"초록선": ["강남역", "잠실역"]},
    "강남역": {"초록선": ["사당역", "종합운동장역"], "분홍선": ["고속터미널역", "군포역"]},
    "신도림역": {"초록선": ["사당역", "합정역"]},
    "합정역": {"초록선": ["신도림역", "신촌역"]},
    "주안역": {"빨간선": ["인천시청역", "부평역"]},
    "인천시청역": {"빨간선": ["주안역", "인천터미널역"]},
    "인천터미널역": {"빨간선": ["인천시청역", "원인재역"]},
    "원인재역": {"빨간선": ["인천터미널역", "월곶역"]},
    "월곶역": {"빨간선": ["원인재역", "중앙역"]},
    "부평역": {"빨간선": ["주안역", "구로역"], "보라선": ["대곡역", "까치산역"]},
    "구로역": {"빨간선": ["부평역", "종로3가역"]},
    "까치산역": {"보라선": ["신촌역", "부평역"]},
    "종로3가역": {"보라선": ["신촌역", "연천역"], "노란선": ["연신내역", "을지로역"], "빨간선": ["구로역"]},
    "연천역": {"보라선": ["종로3가역", "동두천역"]},
    "동두천역": {"보라선": ["연천역", "의정부역"]},
    "의정부역": {"보라선": ["동두천역", "성신여대역"]},
    "동묘앞역": {"보라선": ["성신여대역", "청량리역"]},
    "청량리역": {"보라선": ["동묘앞역", "별내역"], "회색선": ["창동역", "수서역"]},
    "별내역": {"보라선": ["청량리역"]},
    "대화역": {"노란선": ["대곡역"]},
    "대곡역": {"노란선": ["대화역", "구파발역"], "보라선": ["부평역"]},
    "구파발역": {"노란선": ["대곡역", "연신내역"]},
    "연신내역": {"노란선": ["구파발역", "종로3가역"]},
    "을지로역": {"노란선": ["종로3가역", "서울역"]},
    "도곡역": {"노란선": ["잠실역", "수서역"]},
    "수서역": {"노란선": ["도곡역", "오금역"], "회색선": ["청량리역", "성남역"]},
    "오금역": {"노란선": ["수서역"]},
    "충무로역": {"분홍선": ["용산역", "시청역"]},
    "고속터미널역": {"분홍선": ["용산역", "강남역"]},
    "군포역": {"분홍선": ["강남역", "의왕역"]},
    "의왕역": {"분홍선": ["군포역", "수원역"]},
    "수원역": {"분홍선": ["의왕역", "평택역"], "회색선": ["기흥역", "고색역"]},
    "평택역": {"분홍선": ["수원역", "천안역"]},
    "천안역": {"분홍선": ["평택역"]},
    "성남역": {"회색선": ["수서역", "기흥역"]},
    "기흥역": {"회색선": ["성남역", "수원역"]},
    "고색역": {"회색선": ["수원역", "오목천역"]},
    "오목천역": {"회색선": ["고색역"]}
}
for s, lines in list(SUBWAY_GRAPH.items()):
    for l, conns in lines.items():
        for c in conns:
            if c not in SUBWAY_GRAPH: SUBWAY_GRAPH[c] = {}
            if l not in SUBWAY_GRAPH[c]: SUBWAY_GRAPH[c][l] = []
            if s not in SUBWAY_GRAPH[c][l]: SUBWAY_GRAPH[c][l].append(s)

subway_games = {}

async def play_subway_bgm(target, filename):
    if hasattr(target, "response"): 
        author = target.user; guild = target.guild
    elif hasattr(target, "author"):
        author = target.author; guild = target.guild
    else:
        author = None; guild = target.guild

    vc = guild.voice_client
    if vc is None or not vc.is_connected():
        if author and getattr(author, "voice", None):
            vc = await author.voice.channel.connect()
        else:
            return 
    elif author and getattr(author, "voice", None) and vc.channel != author.voice.channel:
        await vc.move_to(author.voice.channel)

    file_path = os.path.join(SUBWAY_BGM_DIR, filename)
    if not os.path.exists(file_path): return

    if vc.is_playing(): vc.stop()
    ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg")
    try:
        vc.play(discord.FFmpegPCMAudio(file_path, executable=ffmpeg_path if os.path.exists(ffmpeg_path) else "ffmpeg"))
    except: pass

class SubwayPlayer:
    def __init__(self, member, role, item):
        self.member = member
        self.role = role # "thief" or "detective"
        self.current_station = "서울역"
        self.current_line = "하늘선"
        self.facing_station = "용산역"
        self.inventory = [item]
        self.bullets = 1 if role == "detective" else 0
        self.debuffs = {"rest": 0, "smart_tag": 0, "smart_tag_owner": None, "bike_penalty": False}
        self.path_history = [] # 턴별 이동 경로 저장
        self.recent_path = [] # 최근 2턴 방문 역 전체 목록
        self.cctv_count = 3 if item == "CCTV" else 0
        self.carried_bomb = False
        self.bomb_timer = 0
        self.is_alive = True
        self.newly_acquired = [] # 이번 턴에 획득한 보급품 목록
        self.personal_msgs = [] # 개인 메시지 큐 추가

class SubwayPsychGame:
    def __init__(self, cid, host, players, thief_id):
        self.cid = cid
        self.host = host
        self.turn = 1
        self.players = players # {id: SubwayPlayer}
        self.thief_id = thief_id
        
        self.bomb_station = ""
        self.fuse_station = ""
        self.terror_station = ""
        self.police_lines = set()
        self.traps = {} # {station: owner_id}
        self.cctvs = {} # {station: owner_id}
        self.cctv_triggers = {} # {station: 남은 횟수}
        self.drones = [] # [{"line":, "current_idx":, "owner_id":, "direction":, "current_station":}]
        self.supply_station = None
        
        self.terror_countdown = 0
        self.turn_actions = {}
        self.logs = []
        
        self.voting_turn = False # 다음 턴이 투표 라운드인지 여부
        self.active_vote_target = None # 투표 대상자 ID
        self.vote_callers = set() # 투표를 이미 발의한 사람 추적
        self.wanted_target = None # 현재 현상수배범 ID
        self.wanted_timer = 0 # 3턴 주기 핑 타이머
        
        # [작업 지시 1] 긴급 투표 동시 발의 여부 상태 변수
        self.is_vote_called_this_turn = False
        
        self.init_map()

    def init_map(self):
        all_stations = list(SUBWAY_GRAPH.keys())
        self.bomb_station = random.choice(all_stations)
        self.fuse_station = random.choice([s for s in all_stations if s != self.bomb_station])
        self.terror_station = random.choice([s for s in all_stations if s not in [self.bomb_station, self.fuse_station]])
        
        for p in self.players.values():
            start_station = random.choice(all_stations)
            p.current_station = start_station
            p.current_line = random.choice(list(SUBWAY_GRAPH[start_station].keys()))
            conns = SUBWAY_GRAPH[start_station][p.current_line]
            p.facing_station = random.choice(conns)

def get_forward_path(line, current, facing, limit=None):
    path = []
    curr = current
    nxt = facing
    while nxt:
        if nxt in path or nxt == current: break # 순환선 무한루프 방지
        path.append(nxt)
        if limit and len(path) >= limit: break
        conns = SUBWAY_GRAPH.get(nxt, {}).get(line, [])
        next_candidates = [c for c in conns if c != curr]
        if not next_candidates: break
        curr = nxt
        nxt = next_candidates[0]
    return path

def get_bfs_dist(start, end):
    if start == end: return 0
    adj = {}
    for s, lines in SUBWAY_GRAPH.items():
        adj[s] = set()
        for l, conns in lines.items():
            for c in conns: adj[s].add(c)
    
    queue = [(start, 0)]
    visited = {start}
    while queue:
        curr, dist = queue.pop(0)
        if curr == end: return dist
        for n in adj.get(curr, []):
            if n not in visited:
                visited.add(n)
                queue.append((n, dist + 1))
    return 999

class SubwayJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=60.0)
        self.host = host
        self.players = [host]

    @discord.ui.button(label="🚇 지하철 탑승 (참여)", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user in self.players:
            await interaction.followup.send("이미 참여 중입니다!", ephemeral=True)
            return
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        embed.description = f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n(최소 3명 필요)"
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="🚀 게임 시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user != self.host:
            await interaction.followup.send("방장만 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 3:
            await interaction.followup.send("최소 3명 이상 필요합니다!", ephemeral=True)
            return
            
        items_info = {
            "천리안": "홀수 턴마다 정방향 경로 5칸 내에 범인이 있는지 감지합니다.",
            "탐지견": "현재 역과 범인이 1칸 거리(인접역) 내에 있는지 확인합니다.",
            "통신망": "매 턴 무작위 플레이어 1명의 선택 행동(이동/환승 등)을 확인합니다.",
            "노선 스캔망": "현재 가장 많은 플레이어가 있는 노선을 확인합니다.",
            "교통카드 내역": "범인이 최근 2턴 내에 현재 역을 지나갔는지 확인합니다.",
            "마이크": "자신과 가장 가까운 사람과의 거리를 칸수로 확인합니다.",
            "망원경": "모든 플레이어 중 자신이 범인과 가장 먼 거리에 있는지 확인합니다.",
            "폭탄 탐지기": "현재 역에 폭탄이 있는지 감지하며, 형사일 경우 발견 시 즉시 수거합니다 (3턴 후 강제 드랍).",
            "자전거": "역방향 전환 시 휴식 페널티가 없으며, 정방향 이동 시 최대 3칸으로 제한됩니다.",
            "CCTV": "설치 시 범인이 해당 역을 지나거나 멈추면 알림을 받습니다 (총 3회).",
            "폴리스 라인": "[1회용] 특정 역을 영구 폐쇄합니다. 게임 끝까지 누구도 통과하거나 멈출 수 없습니다.",
            "덫": "현재 역에 덫을 설치합니다. 지나가는 유저는 멈추고, 멈추는 유저는 1턴 휴식합니다. (1회용)",
            "드론": "특정 노선을 따라 매 턴 1칸씩 정찰하며 유저 발견 시 보고합니다. (1회용)",
            "스마트 태그": "[액티브] 같은 역 사람에게 부착. 2턴간 위치 추적. (비소모성: 조건 만족 시 계속 사용 가능)"
        }
        
        items_list = list(items_info.keys())
        thief = random.choice(self.players)
        game_players = {}
        for p in self.players:
            role = "thief" if p.id == thief.id else "detective"
            if role == "thief":
                thief_items = [i for i in items_list if i != "폭탄 탐지기"]
                item = random.choice(thief_items)
            else:
                item = random.choice(items_list)
            game_players[p.id] = SubwayPlayer(p, role, item)
            
        game = SubwayPsychGame(interaction.channel_id, self.host, game_players, thief.id)
        subway_games[interaction.channel_id] = game
        
        if interaction.guild.voice_client: interaction.guild.voice_client.stop()
        try: await play_subway_bgm(interaction, "subway.mp3")
        except: pass
        
        bomb_line = random.choice(list(SUBWAY_GRAPH[game.bomb_station].keys()))
        for pid, p in game.players.items():
            desc = items_info.get(p.inventory[0], "설명이 없습니다.")
            msg = f"🛡️ **당신의 역할:** {'도둑' if p.role == 'thief' else '형사'}\n🎁 **지급 아이템:** {p.inventory[0]}\n📜 **능력 설명:** {desc}\n"
            if p.role == "thief":
                msg += f"\n📍 **폭탄 노선:** {bomb_line}\n📍 **도화선 역:** {game.fuse_station}\n(폭탄을 획득하면 테러 장소가 공개됩니다!)"
            try: await p.member.send(msg)
            except: pass
        
        try: await interaction.edit_original_response(content="🚇 **[지하철 심리 추격전]을 시작합니다!**", embed=None, view=None)
        except: pass
        await start_subway_turn(interaction.channel, game)

async def start_subway_turn(channel, game):
    if game.cid not in subway_games: return
    if game.voting_turn:
        view = SubwayVoteView(game)
        embed = discord.Embed(title="🚨 [긴급 투표] 현상수배 지정 투표", color=0xE74C3C)
        target_name = game.players[game.active_vote_target].member.display_name
        embed.description = f"**대상자:** {target_name}\n\n이번 라운드는 이동 없이 찬반 투표가 진행됩니다.\n찬성이 과반수(전체 생존자의 50% 초과)일 경우 해당 유저는 **현상수배범**으로 지정됩니다."
        await channel.send(embed=embed, view=view)
        return

    embed = discord.Embed(title=f"🚇 [지하철 심리 추격전] 제 {game.turn}턴", color=0x34495E)
    embed.description = "턴이 시작되었습니다! 아래 버튼을 눌러 자신의 현재 위치를 확인하고 행동을 선택하세요.\n(모든 정보는 본인에게만 비공개로 표시됩니다.)"
    
    if game.turn % 4 == 0:
        # [작업 지시 2-1] 폴리스 라인으로 폐쇄된 역은 제외
        available_stations = [s for s in SUBWAY_GRAPH.keys() if s not in game.police_lines]
        if available_stations:
            game.supply_station = random.choice(available_stations)
            embed.add_field(name="🎁 보급품 투하!", value=f"**{game.supply_station}**에 보급품이 떨어졌습니다!", inline=False)
        else:
            game.supply_station = None
        
    view = SubwayTurnStartView(game)
    await channel.send(embed=embed, view=view)
    await check_subway_all_acted(game)

class SubwayVoteView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game
        self.votes = {} # {pid: choice} (1: 찬성, -1: 반대, 0: 기권)
        self.acted_pids = set()

    async def check_all_voted(self, interaction):
        alive_players = [p for p in self.game.players.values() if p.is_alive]
        if len(self.acted_pids) >= len(alive_players):
            self.stop()
            # 결과 집계
            pro = sum(1 for v in self.votes.values() if v == 1)
            con = sum(1 for v in self.votes.values() if v == -1)
            total_voters = len(alive_players)
            
            target = self.game.players[self.game.active_vote_target]
            target_name = target.member.display_name
            
            channel = interaction.channel if interaction else bot.get_channel(self.game.cid)
            if not channel: return

            if pro > total_voters / 2:
                self.game.wanted_target = self.game.active_vote_target
                self.game.wanted_timer = 4
                await channel.send(f"🚨 **[긴급 속보]** 투표 통과! **{target_name}**님이 현상수배범으로 지정되었습니다!\n📍 **[즉시 공개] 현재 위치:** {target.current_station} ({target.current_line})")
            else:
                await channel.send(f"⚖️ 투표 부결! 증거 불충분으로 **{target_name}**님의 현상수배가 기각되었습니다. (찬성 {pro}, 반대 {con})")
            
            # 상태 리셋 및 복귀
            self.game.voting_turn = False
            self.game.active_vote_target = None
            self.game.turn_actions = {}
            self.game.is_vote_called_this_turn = False
            
            for p in self.game.players.values(): p.personal_msgs.clear()
            await asyncio.sleep(3)
            await start_subway_turn(channel, self.game)

    @discord.ui.button(label="👍 찬성", style=discord.ButtonStyle.success)
    async def pro_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players or not self.game.players[interaction.user.id].is_alive:
            await interaction.response.send_message("참여 권한이 없습니다.", ephemeral=True); return
        if interaction.user.id in self.acted_pids:
            await interaction.response.send_message("이미 투표했습니다.", ephemeral=True); return
        
        self.votes[interaction.user.id] = 1
        self.acted_pids.add(interaction.user.id)
        
        p = self.game.players[interaction.user.id]
        msg = "👍 찬성표를 던졌습니다 (익명)."
        if p.personal_msgs:
            msg += "\n\n" + "🔔 **[개인 수사 정보]**\n" + "\n".join(p.personal_msgs)
            
        await interaction.response.send_message(msg, ephemeral=True)
        await self.check_all_voted(interaction)

    @discord.ui.button(label="👎 반대", style=discord.ButtonStyle.danger)
    async def con_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players or not self.game.players[interaction.user.id].is_alive:
            await interaction.response.send_message("참여 권한이 없습니다.", ephemeral=True); return
        if interaction.user.id in self.acted_pids:
            await interaction.response.send_message("이미 투표했습니다.", ephemeral=True); return
        
        self.votes[interaction.user.id] = -1
        self.acted_pids.add(interaction.user.id)
        
        p = self.game.players[interaction.user.id]
        msg = "👎 반대표를 던졌습니다 (익명)."
        if p.personal_msgs:
            msg += "\n\n" + "🔔 **[개인 수사 정보]**\n" + "\n".join(p.personal_msgs)
            
        await interaction.response.send_message(msg, ephemeral=True)
        await self.check_all_voted(interaction)

    @discord.ui.button(label="⏭️ 기권", style=discord.ButtonStyle.secondary)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players or not self.game.players[interaction.user.id].is_alive:
            await interaction.response.send_message("참여 권한이 없습니다.", ephemeral=True); return
        if interaction.user.id in self.acted_pids:
            await interaction.response.send_message("이미 투표했습니다.", ephemeral=True); return
        
        self.votes[interaction.user.id] = 0
        self.acted_pids.add(interaction.user.id)
        
        p = self.game.players[interaction.user.id]
        msg = "⏭️ 투표를 기권했습니다."
        if p.personal_msgs:
            msg += "\n\n" + "🔔 **[개인 수사 정보]**\n" + "\n".join(p.personal_msgs)
            
        await interaction.response.send_message(msg, ephemeral=True)
        await self.check_all_voted(interaction)

class SubwayTurnStartView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="🎮 내 행동 선택", style=discord.ButtonStyle.success)
    async def select_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id not in self.game.players:
            await interaction.followup.send("❌ 게임 참여자가 아닙니다.", ephemeral=True)
            return
            
        p = self.game.players[interaction.user.id]
        if not p.is_alive:
            await interaction.followup.send("💀 당신은 이미 탈락했습니다.", ephemeral=True)
            return

        if interaction.user.id in self.game.turn_actions:
            await interaction.followup.send("✅ 이미 이번 턴의 행동을 예약했습니다.", ephemeral=True)
            return

        view = SubwayActionView(self.game, interaction.user.id)
        msg = f"🚇 **현재 위치:** {p.current_station} ({p.current_line})\n👉 **진행 방향:** {p.facing_station} 방면"
        if p.personal_msgs:
            msg += "\n\n" + "🔔 **[개인 수사 정보]**\n" + "\n".join(p.personal_msgs)
        await interaction.followup.send(msg, view=view, ephemeral=True)

class SubwayActionView(discord.ui.View):
    def __init__(self, game, pid):
        super().__init__(timeout=None)
        self.game = game
        self.pid = pid
        self.p = game.players[pid]
        
        # 3. 이동 관련 버튼
        is_resting = self.p.debuffs.get("rest", 0) > 0
        btn_move = discord.ui.Button(label="🏃 정방향 이동", style=discord.ButtonStyle.primary, disabled=is_resting)
        btn_move.callback = self.move_fwd_cb; self.add_item(btn_move)

        if len(SUBWAY_GRAPH[self.p.current_station].keys()) > 1:
            btn_transfer = discord.ui.Button(label="🔄 환승하기", style=discord.ButtonStyle.secondary, disabled=is_resting)
            btn_transfer.callback = self.transfer_cb; self.add_item(btn_transfer)

        conns = SUBWAY_GRAPH[self.p.current_station][self.p.current_line]
        if len(conns) > 1:
            btn_rev = discord.ui.Button(label="↩️ 역방향 전환", style=discord.ButtonStyle.grey, disabled=is_resting)
            btn_rev.callback = self.reverse_cb; self.add_item(btn_rev)

        if is_resting:
            btn_wait = discord.ui.Button(label="🛌 휴식 (턴 넘기기)", style=discord.ButtonStyle.secondary)
            btn_wait.callback = self.rest_wait_cb; self.add_item(btn_wait)

        # 4. 특수 행동 버튼
        if self.p.role == "detective" and self.p.bullets > 0:
            others = [pp for pp in game.players.values() if pp.current_station == self.p.current_station and pp.member.id != self.pid and pp.is_alive]
            if others:
                btn_shoot = discord.ui.Button(label="🔫 권총 발포", style=discord.ButtonStyle.danger, disabled=is_resting)
                btn_shoot.callback = self.shoot_cb; self.add_item(btn_shoot)

        # 5. 액티브 아이템 버튼 (인벤토리 기반)
        if "폴리스 라인" in self.p.inventory:
            btn = discord.ui.Button(label="🚧 폴리스 라인", style=discord.ButtonStyle.danger, disabled=is_resting)
            btn.callback = self.police_cb; self.add_item(btn)
        if "스마트 태그" in self.p.inventory:
            others = [pp for pp in self.game.players.values() if pp.current_station == self.p.current_station and pp.member.id != self.pid and pp.is_alive]
            if others:
                btn = discord.ui.Button(label="📍 스마트 태그", style=discord.ButtonStyle.grey, disabled=is_resting)
                btn.callback = self.tag_cb; self.add_item(btn)
        if self.p.role == "thief" and "폭탄" in self.p.inventory and "도화선" in self.p.inventory and self.p.current_station == self.game.terror_station:
            btn = discord.ui.Button(label="💣 테러 시작", style=discord.ButtonStyle.danger, disabled=is_resting)
            btn.callback = self.terror_cb; self.add_item(btn)

        # 6. 긴급 투표 발의 버튼
        can_call_vote = (self.pid not in self.game.vote_callers) and (not is_resting) and (self.game.wanted_target is None)
        btn_vote = discord.ui.Button(label="📢 긴급 투표 발의", style=discord.ButtonStyle.danger, disabled=not can_call_vote)
        btn_vote.callback = self.call_vote_cb; self.add_item(btn_vote)

    async def call_vote_cb(self, interaction: discord.Interaction):
        if self.pid in self.game.turn_actions: return
        
        # [작업 지시 1] 동시 발의 여부 상태 변수 검사
        if self.game.is_vote_called_this_turn:
            await interaction.response.send_message("❌ 이번 라운드에 이미 다른 누군가가 긴급 투표를 발의했습니다.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        others = [pp for pp in self.game.players.values() if pp.member.id != self.pid and pp.is_alive]
        if not others:
            await interaction.followup.send("❌ 투표할 대상이 없습니다.", ephemeral=True); return
            
        opts = [discord.SelectOption(label=pp.member.display_name, value=str(pp.member.id)) for pp in others]
        sel = discord.ui.Select(placeholder="현상수배로 지정할 플레이어 선택", options=opts)
        
        async def sel_cb(i: discord.Interaction):
            await i.response.defer(ephemeral=True)
            target_id = int(i.data['values'][0])
            self.game.turn_actions[self.pid] = {"type": "call_vote", "target": target_id}
            self.game.is_vote_called_this_turn = True
            await i.edit_original_response(content=f"✅ {self.game.players[target_id].member.display_name}님을 대상으로 긴급 투표를 발의했습니다.", view=None)
            await check_subway_all_acted(self.game)
            
        sel.callback = sel_cb
        v = discord.ui.View(); v.add_item(sel)
        await interaction.edit_original_response(content="현상수배를 발의할 타겟을 선택하세요:", view=v)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.pid:
            await interaction.response.send_message("자신의 행동만 선택할 수 있습니다!", ephemeral=True)
            return False
        return True

    async def rest_wait_cb(self, interaction: discord.Interaction):
        if self.pid in self.game.turn_actions: return
        await interaction.response.defer(ephemeral=True)
        self.game.turn_actions[self.pid] = {"type": "wait"}
        await interaction.edit_original_response(content="🛌 턴을 넘겼습니다. 다른 플레이어를 기다리세요.", view=None)
        await check_subway_all_acted(self.game)

    async def move_fwd_cb(self, interaction: discord.Interaction):
        if self.pid in self.game.turn_actions: return
        await interaction.response.defer(ephemeral=True)
        if self.p.debuffs["rest"] > 0:
            self.game.turn_actions[self.pid] = {"type": "rest_wait"}
            await interaction.edit_original_response(content="🛌 이번 턴은 휴식해야 합니다. (자동 휴식 처리됨)", view=None)
            await check_subway_all_acted(self.game)
            return
        if self.p.debuffs.get("bike_penalty", False):
            limit = 3
        elif self.p.role == "thief":
            limit = 5
        else:
            limit = None

        path = get_forward_path(self.p.current_line, self.p.current_station, self.p.facing_station, limit=limit)
        if not path:
            await interaction.followup.send("❌ 종점에 도달했습니다. '역방향 전환'을 눌러 방향을 바꿔주세요.", ephemeral=True); return
        await interaction.edit_original_response(view=None)
        view = SubwayDestSelectView(self.game, self.pid, path)
        await interaction.followup.send("목적지를 선택하세요:", view=view, ephemeral=True)

    async def transfer_cb(self, interaction: discord.Interaction):
        if self.pid in self.game.turn_actions: return
        await interaction.response.defer(ephemeral=True)
        if self.p.debuffs["rest"] > 0:
            self.game.turn_actions[self.pid] = {"type": "rest_wait"}
            await interaction.edit_original_response(content="🛌 휴식 중에는 환승할 수 없습니다. (자동 휴식 처리됨)", view=None)
            await check_subway_all_acted(self.game)
            return
        lines = [l for l in SUBWAY_GRAPH[self.p.current_station].keys()]
        target_lines = [l for l in lines if l != self.p.current_line]
        await interaction.edit_original_response(view=None)
        view = SubwayLineSelectView(self.game, self.pid, target_lines)
        await interaction.followup.send("갈아탈 노선을 선택하세요 (다음 턴 휴식):", view=view, ephemeral=True)

    async def reverse_cb(self, interaction: discord.Interaction):
        if self.pid in self.game.turn_actions: return
        await interaction.response.defer(ephemeral=True)
        if self.p.debuffs["rest"] > 0:
            self.game.turn_actions[self.pid] = {"type": "rest_wait"}
            await interaction.edit_original_response(content="🛌 휴식 중에는 방향을 틀 수 없습니다. (자동 휴식 처리됨)", view=None)
            await check_subway_all_acted(self.game)
            return
        conns = SUBWAY_GRAPH[self.p.current_station][self.p.current_line]
        rev_candidates = [c for c in conns if c != self.p.facing_station]
        self.game.turn_actions[self.pid] = {"type": "reverse", "new_facing": rev_candidates[0]}
        await interaction.followup.send(f"✅ {rev_candidates[0]} 방면으로 방향을 전환했습니다.", ephemeral=True)
        await check_subway_all_acted(self.game)

    async def police_cb(self, interaction):
        if self.pid in self.game.turn_actions: return
        await interaction.response.defer(ephemeral=True)
        opts = [discord.SelectOption(label=s, value=s) for s in list(SUBWAY_GRAPH[self.p.current_station][self.p.current_line])]
        sel = discord.ui.Select(placeholder="폐쇄할 인접 역 선택", options=opts)
        async def sel_cb(i):
            await i.response.defer(ephemeral=True)
            self.game.turn_actions[self.pid] = {"type": "police", "target": i.data['values'][0]}
            await i.edit_original_response(content=f"✅ {i.data['values'][0]}를 영구 폐쇄합니다.", view=None)
            await check_subway_all_acted(self.game)
        sel.callback = sel_cb
        v = discord.ui.View(); v.add_item(sel)
        await interaction.edit_original_response(content="폐쇄할 역을 고르세요 (1턴 소모):", view=v)

    async def tag_cb(self, interaction):
        if self.pid in self.game.turn_actions: return
        await interaction.response.defer(ephemeral=True)
        self.game.turn_actions[self.pid] = {"type": "tag"}
        await interaction.edit_original_response(content="✅ 이번 턴 이동 후 같은 역 사람에게 태그를 붙입니다.", view=None)
        await check_subway_all_acted(self.game)

    async def terror_cb(self, interaction):
        if self.pid in self.game.turn_actions: return
        await interaction.response.defer(ephemeral=True)
        self.game.turn_actions[self.pid] = {"type": "terror"}
        await interaction.edit_original_response(content="✅ 테러 카운트다운을 시작합니다!", view=None)
        await check_subway_all_acted(self.game)



    async def shoot_cb(self, interaction: discord.Interaction):
        if self.pid in self.game.turn_actions: return
        await interaction.response.defer(ephemeral=True)
        self.game.turn_actions[self.pid] = {"type": "shoot"}
        await interaction.followup.send("✅ 발포를 예약했습니다. (턴 정산 시 결과 공개)", ephemeral=True)
        await check_subway_all_acted(self.game)

class SubwayDestSelectView(discord.ui.View):
    def __init__(self, game, pid, path):
        super().__init__(timeout=None)
        self.game = game
        self.pid = pid
        opts = [discord.SelectOption(label=f"{i+1}칸: {s}", value=s) for i, s in enumerate(path[:25])]
        sel = discord.ui.Select(placeholder="목적지 선택", options=opts)
        sel.callback = self.cb
        self.add_item(sel)

    async def cb(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dest = interaction.data['values'][0]
        self.game.turn_actions[self.pid] = {"type": "move", "dest": dest}
        await interaction.edit_original_response(content=f"✅ {dest}(으)로 이동을 예약했습니다.", view=None)
        await interaction.followup.send(f"✅ {dest}(으)로 이동이 예약되었습니다.", ephemeral=True)
        await check_subway_all_acted(self.game)

class SubwayLineSelectView(discord.ui.View):
    def __init__(self, game, pid, lines):
        super().__init__(timeout=None)
        self.game = game
        self.pid = pid
        self.p = game.players[pid]
        opts = []
        for line in lines:
            for adj in SUBWAY_GRAPH[self.p.current_station][line]:
                opts.append(discord.SelectOption(label=f"{line} ({adj} 방면)", value=f"{line}|{adj}"))
        
        sel = discord.ui.Select(placeholder="노선 및 방향 선택", options=opts)
        sel.callback = self.cb; self.add_item(sel)

    async def cb(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        line_name, target = interaction.data['values'][0].split("|")
        self.game.turn_actions[self.pid] = {"type": "transfer", "line": line_name, "target": target}
        await interaction.edit_original_response(content=f"✅ {line_name}({target} 방면)으로 환승을 예약했습니다.", view=None)
        await interaction.followup.send(f"✅ {line_name}({target} 방면)으로 환승이 예약되었습니다.", ephemeral=True)
        await check_subway_all_acted(self.game)

# SubwaySetupView는 자동화 처리로 인해 삭제되었습니다.



async def check_subway_all_acted(game):
    if game.cid not in subway_games: return
    if getattr(game, 'is_processing', False): return
    alive = [p for p in game.players.values() if p.is_alive]
    acted = [pid for pid in game.turn_actions.keys() if game.players[pid].is_alive]
    if len(acted) >= len(alive):
        await check_subway_turn_end(game)

async def check_subway_turn_end(game):
    if game.cid not in subway_games: return
    if getattr(game, 'is_processing', False): return
    game.is_processing = True
    for p in game.players.values(): p.personal_msgs.clear()
    channel = bot.get_channel(game.cid)
    game.logs = [f"--- 제 {game.turn}턴 정산 결과 ---"]
    
    # 1. 자동 아이템 및 행동 처리
    for pid, p in game.players.items():
        if not p.is_alive: continue
        
        # 인벤토리 기반 완전 자동화 (Task 1)
        while "CCTV" in p.inventory and p.cctv_count > 0:
            # [작업 지시 2-2] 폐쇄된 역 제외
            available_stations = [s for s in SUBWAY_GRAPH.keys() if s not in game.police_lines]
            targets = random.sample(available_stations, min(3, len(available_stations)))
            for s in targets:
                game.cctvs[s] = pid
                game.cctv_triggers[s] = 3
            p.cctv_count = max(0, p.cctv_count - 3)
            p.inventory.remove("CCTV")
            game.logs.append("📸 누군가 무작위 3곳에 CCTV를 설치했습니다.")
            
        if "덫" in p.inventory:
            # [작업 지시 2-2] 폐쇄된 역 제외
            available_stations = [s for s in SUBWAY_GRAPH.keys() if s not in game.police_lines]
            if available_stations:
                s = random.choice(available_stations)
                game.traps[s] = pid
                if "덫" in p.inventory: p.inventory.remove("덫")
                game.logs.append("🪤 어둠 속에서 누군가 덫을 설치하는 소리가 들렸습니다...")
                p.personal_msgs.append(f"🪤 [비밀 메시지] 당신의 덫이 무작위 위치인 [{s}]에 설치되었습니다!")
            
        if "드론" in p.inventory:
            line = random.choice(list(SUBWAY_GRAPH[p.current_station].keys()))
            nxt = SUBWAY_GRAPH[p.current_station][line][0]
            game.drones.append({"line": line, "current_station": p.current_station, "facing_station": nxt, "owner_id": pid, "just_deployed": True})
            if "드론" in p.inventory: p.inventory.remove("드론")
            game.logs.append("🛸 어디선가 드론이 날아오르는 소리가 들렸습니다.")

        # 유저 예약 행동 처리
        act = game.turn_actions.get(pid, {"type": "wait"})
        if act["type"] == "police":
            game.police_lines.add(act["target"]); p.debuffs["rest"] = 1; game.logs.append(f"🚧 {p.member.display_name}님이 {act['target']}를 폐쇄했습니다.")
            if "폴리스 라인" in p.inventory: p.inventory.remove("폴리스 라인")
        
        p.recent_path = [s for path in p.path_history for s in path]

    # 3. 이동 페이즈
    player_paths = {}
    for pid, p in game.players.items():
        if not p.is_alive: continue
        act = game.turn_actions.get(pid, {"type": "wait"})
        
        if p.debuffs["rest"] > 0 or act["type"] == "rest_wait":
            if p.debuffs["rest"] > 0: p.debuffs["rest"] -= 1
            player_paths[pid] = [p.current_station]; continue
            
        if act["type"] == "police":
            player_paths[pid] = [p.current_station]; continue
            
        actual_path = [p.current_station]
        if act["type"] == "move":
            p.debuffs["bike_penalty"] = False # 페널티 1회 소모 후 정상화
            line_path = get_forward_path(p.current_line, p.current_station, p.facing_station)
            for s in line_path:
                if s in game.police_lines:
                    game.logs.append(f"🛑 {p.member.display_name}님이 폐쇄된 {s} 앞에서 멈췄습니다!"); break
                actual_path.append(s)
                if s in game.traps and game.traps[s] != pid:
                    game.logs.append(f"🪤 {p.member.display_name}님이 {s}에서 덫에 걸려 멈췄습니다!")
                    if s == act["dest"]:
                        p.debuffs["rest"] = 1; game.logs.append(f"🛌 {p.member.display_name}님이 덫을 밟아 다음 턴 휴식합니다!")
                    owner_pid = game.traps[s]
                    owner = game.players.get(owner_pid)
                    del game.traps[s]
                    if owner and owner.is_alive:
                        target_s = owner.current_station
                        if target_s in game.police_lines or target_s in game.traps:
                            empty_stations = [st for st in SUBWAY_GRAPH.keys() if st not in game.traps and st not in game.police_lines]
                            if empty_stations:
                                target_s = random.choice(empty_stations)
                        game.traps[target_s] = owner_pid
                    break
                if s == act["dest"]: break
            p.current_station = actual_path[-1]
            # 방향 및 자동 유턴 업데이트
            nxt_conns = [c for c in SUBWAY_GRAPH[p.current_station][p.current_line] if c not in actual_path[-2:]]
            if nxt_conns: p.facing_station = nxt_conns[0]
            else: # 유턴
                p.facing_station = SUBWAY_GRAPH[p.current_station][p.current_line][0]
        elif act["type"] == "transfer":
            if p.current_station in game.police_lines:
                game.logs.append(f"🛑 {p.member.display_name}님이 폴리스 라인이 설치된 역에서 환승할 수 없었습니다!")
            else:
                p.current_line = act["line"]; p.debuffs["rest"] = 1; p.facing_station = act["target"]
        elif act["type"] == "reverse":
            p.facing_station = act["new_facing"]
            if "자전거" not in p.inventory: 
                p.debuffs["rest"] = 1
            else: 
                p.debuffs["bike_penalty"] = True  # 자전거 혜택을 본 대신 다음 이동에 3칸 제약 부여
        player_paths[pid] = actual_path
        p.path_history.append(actual_path)
        p.path_history = p.path_history[-2:]
        p.recent_path = [s for path in p.path_history for s in path]

    # 2. 사살 판정 (이동 후 위치 기준 - Task 4)
    thief = game.players[game.thief_id]
    for pid, act in game.turn_actions.items():
        p = game.players[pid]
        if act["type"] == "shoot":
            if p.current_station == thief.current_station:
                game.is_processing = False
                await channel.send(f"💥 **타탕!** {p.member.mention} 형사가 같은 역에 있던 {thief.member.mention} 도둑을 저격했습니다!"); await end_subway(game, "detective"); return
            else:
                innocent = [pp for pp in game.players.values() if pp.current_station == p.current_station and pp.role == "detective" and pp.member.id != pid and pp.is_alive]
                if innocent:
                    game.is_processing = False
                    await channel.send(f"💀 **오사!** {p.member.mention} 형사가 무고한 {innocent[0].member.mention}를 쐈습니다!"); await end_subway(game, "thief_accident"); return
            p.bullets -= 1

    # 3. 보급품 및 아이템 알림
    if game.supply_station:
        supplies_to_remove = set()
        for pid, path in player_paths.items():
            if game.supply_station == path[-1]: # 최종 목적지 도착 판정
                p = game.players[pid]
                supply_items = ["천리안", "탐지견", "통신망", "노선 스캔망", "교통카드 내역", "마이크", "망원경", "폭탄 탐지기", "자전거", "CCTV", "폴리스 라인", "덫", "드론", "스마트 태그"]
                if p.role == "thief":
                    supply_items.remove("폭탄 탐지기")
                new = random.choice(supply_items)
                p.inventory.append(new); p.newly_acquired.append(new)
                if new == "CCTV": p.cctv_count += 3
                game.logs.append(f"🎁 {p.member.display_name}님이 보급품({new})을 획득했습니다!")
                supplies_to_remove.add(game.supply_station)
        if supplies_to_remove:
            game.supply_station = None

    thief = game.players[game.thief_id]
    if thief.current_station == game.bomb_station:
        if "폭탄" not in thief.inventory:
            thief.inventory.append("폭탄"); game.logs.append("💣 도둑이 폭탄을 확보했습니다!")
            game.bomb_station = "도둑"
            thief.personal_msgs.append(f"⚠️ **폭탄을 확보했습니다!**\n📍 테러 장소: **{game.terror_station}**\n장소로 이동해 테러를 시작하세요!")
    if thief.current_station == game.fuse_station:
        if "도화선" not in thief.inventory: thief.inventory.append("도화선"); game.logs.append("🧨 도둑이 도화선을 확보했습니다!")

    # 4. 아이템 사후 처리
    for pid, p in game.players.items():
        if not p.is_alive: continue
        if p.debuffs["smart_tag"] > 0:
            owner = game.players[p.debuffs["smart_tag_owner"]]
            owner.personal_msgs.append(f"🛰️ [스마트 태그] {p.member.display_name} 위치: {p.current_station}")
            p.debuffs["smart_tag"] -= 1
        to_delete = []
        for s, oid in list(game.cctvs.items()):
            if s in player_paths.get(game.thief_id, []):
                game.players[oid].personal_msgs.append(f"📸 [CCTV] {s}에 도둑이 포착되었습니다!")
                game.cctv_triggers[s] -= 1
                if game.cctv_triggers[s] <= 0:
                    to_delete.append(s)
        for s in to_delete:
            if s in game.cctvs: del game.cctvs[s]
            if s in game.cctv_triggers: del game.cctv_triggers[s]
        # 패시브
        if "천리안" in p.inventory:
            if game.turn % 2 == 0:
                fwd = get_forward_path(p.current_line, p.current_station, p.facing_station)
                if thief.current_station in fwd:
                    p.personal_msgs.append("👁️ [천리안] 정방향 경로에 범인이 있습니다!")
            else:
                p.personal_msgs.append("👁️ [천리안] 이번 턴은 능력을 충전 중이라 발동하지 않습니다.")
        if "탐지견" in p.inventory:
            dist = get_bfs_dist(p.current_station, thief.current_station)
            res = "Yes" if dist <= 1 else "No"
            p.personal_msgs.append(f"🐕 [탐지견] 근처에 범인이 있습니까? : {res}")
        if "통신망" in p.inventory:
            targets = [pp for pp in game.players.values() if pp.member.id != pid and pp.is_alive]
            if targets:
                target = random.choice(targets)
                act_type = game.turn_actions.get(target.member.id, {"type": "휴식"})["type"]
                p.personal_msgs.append(f"📡 [통신망] {target.member.display_name}의 행동: {act_type}")
        if "노선 스캔망" in p.inventory:
            counts = {}
            for pp in game.players.values(): counts[pp.current_line] = counts.get(pp.current_line, 0) + 1
            max_val = max(counts.values())
            best_lines = [l for l, c in counts.items() if c == max_val]
            best_str = ", ".join(best_lines)
            p.personal_msgs.append(f"📊 [노선 스캔망] 최다 인원 노선: {best_str}")
        if "교통카드 내역" in p.inventory:
            if game.turn % 2 == 0:
                if p.current_station in thief.recent_path:
                    p.personal_msgs.append(f"💳 [교통카드] 범인이 최근 2턴 내 이곳({p.current_station})을 지나갔습니다!")
            else:
                p.personal_msgs.append("💳 [교통카드] 이번 턴은 내역을 조회할 수 없습니다.")
        if "마이크" in p.inventory:
            dists = [get_bfs_dist(p.current_station, pp.current_station) for pp in game.players.values() if pp.member.id != pid and pp.is_alive]
            if dists:
                p.personal_msgs.append(f"🎤 [마이크] 가장 가까운 사람과의 거리: {min(dists)}칸")
        if "망원경" in p.inventory:
            my_d = get_bfs_dist(p.current_station, thief.current_station)
            all_d = [get_bfs_dist(pp.current_station, thief.current_station) for pp in game.players.values() if pp.role == "detective" and pp.is_alive]
            if all_d:
                if my_d == max(all_d):
                    p.personal_msgs.append("🔭 [망원경] 당신이 범인과 가장 멀리 떨어져 있습니다.")
        if "폭탄 탐지기" in p.inventory:
            if p.carried_bomb:
                p.bomb_timer -= 1
                if p.bomb_timer <= 0:
                    game.bomb_station = p.current_station; p.carried_bomb = False; game.logs.append(f"💣 {p.member.display_name}님이 폭탄을 떨어뜨렸습니다!")
            elif p.current_station == game.bomb_station:
                if p.role == "detective":
                    p.carried_bomb = True; p.bomb_timer = 3; game.bomb_station = "공중"
                    game.logs.append(f"⚡ {p.member.display_name}님이 폭탄을 발견해 수거했습니다!")
                else:
                    p.personal_msgs.append("☢️ [폭탄 탐지기] 이곳에 폭탄이 있습니다!")

    for pid, act in game.turn_actions.items():
        p = game.players[pid]
        if act["type"] == "tag":
            targets = [pp for pp in game.players.values() if pp.current_station == p.current_station and pp.member.id != pid]
            if targets:
                t = random.choice(targets); t.debuffs["smart_tag"] = 2; t.debuffs["smart_tag_owner"] = pid
                game.logs.append(f"📍 {p.member.display_name}님이 누군가에게 태그를 붙였습니다.")
        elif act["type"] == "terror":
            if "폭탄" in p.inventory and "도화선" in p.inventory and p.current_station == game.terror_station:
                game.terror_countdown += 1; game.logs.append(f"🔥 테러 준비 중... ({game.terror_countdown}/10)")
                if game.terror_countdown >= 10: await end_subway(game, "thief"); return

    # 긴급 투표 발의 여부 미리 확인 (카운트다운 보호용)
    vote_requests = []
    for pid, act in game.turn_actions.items():
        if act["type"] == "call_vote":
            vote_requests.append((pid, act["target"]))

    thief_acted = game.turn_actions.get(game.thief_id, {"type": "wait"})
    if thief_acted["type"] != "terror" and not vote_requests:
        game.terror_countdown = 0

    for d in list(game.drones):
        if d.get("just_deployed"):
            d["just_deployed"] = False
            continue
            
        drone_line_data = SUBWAY_GRAPH[d["current_station"]].get(d["line"])
        if not drone_line_data:
            game.drones.remove(d)
            continue
        
        conns = drone_line_data
        nxt = [c for c in conns if c == d["facing_station"]]
        if not nxt: # 종점 도달 시 반전
            d["facing_station"] = conns[0]
            nxt = [d["facing_station"]]
        
        next_station = nxt[0]
        # [작업 지시 2-3] 드론 이동 시 다음 칸이 영구 폐쇄된 역인 경우 블로킹 및 반대로 전환
        if next_station in game.police_lines:
            rev_conns = [c for c in SUBWAY_GRAPH[d["current_station"]][d["line"]] if c != next_station]
            if rev_conns:
                d["facing_station"] = rev_conns[0]
            game.logs.append(f"🛸 {d['current_station']}에서 자동 이동하던 드론이 폴리스 라인으로 폐쇄된 {next_station} 방향 진입에 실패하여 제자리에 멈춘 뒤 방향을 전환했습니다.")
        else:
            # 실제 이동
            d["prev"] = d["current_station"]
            d["current_station"] = next_station
            # 다음 facing 결정 (지정 노선 데이터만 참조)
            new_conns = [c for c in SUBWAY_GRAPH[d["current_station"]][d["line"]] if c != d.get("prev", "")]
            if new_conns: d["facing_station"] = new_conns[0]
            else: d["facing_station"] = SUBWAY_GRAPH[d["current_station"]][d["line"]][0]
            
        at = [pp.member.display_name for pp in game.players.values() if pp.current_station == d["current_station"] and pp.is_alive]
        if at:
            game.players[d["owner_id"]].personal_msgs.append(f"🛸 [드론] {d['current_station']}에서 발견: {', '.join(at)}")

    # 5. 긴급 투표 발의 및 현상수배 핑 로직
    if vote_requests:
        caller_id, target_id = vote_requests[0]
        game.voting_turn = True
        game.active_vote_target = target_id
        game.vote_callers.add(caller_id)
        game.logs.append("🚨 **[긴급 소집]** 누군가 긴급 투표를 발의했습니다! 다음 턴은 이동 없이 찬반 투표가 진행됩니다!")
        
        # 나머지 발의자 처리 (무시되지만 발의권 보존)
        for pid, target in vote_requests[1:]:
            p = game.players[pid]
            game.logs.append(f"⚠️ {p.member.display_name}님의 투표 발의는 다른 안건에 밀렸지만 발의권은 보존됩니다.")
            game.turn_actions[pid] = {"type": "wait"} # 행동 취소

    if game.wanted_target:
        wanted_p = game.players.get(game.wanted_target)
        if wanted_p and wanted_p.is_alive:
            game.wanted_timer -= 1
            if game.wanted_timer <= 0:
                game.logs.append(f"🚨 **[시민 제보]** 현상수배범 **{wanted_p.member.display_name}**의 위치 포착! ➔ **{wanted_p.current_station}**")
                game.wanted_timer = 3

    # 6. 같은 역 조우(Encounter) 시스템
    station_groups = {}
    for p in game.players.values():
        if p.is_alive:
            station_groups.setdefault(p.current_station, []).append(p)
    
    for station, group in station_groups.items():
        if len(group) >= 2:
            for p in group:
                others = [op.member.display_name for op in group if op.member.id != p.member.id]
                other_names = ", ".join(others)
                p.personal_msgs.append(f"👀 [조우] 현재 역에 누군가 있습니다! (함께 있는 사람: {other_names})")

    # 7. 소유자 전용 설치 아이템 위치 요약
    for pid, p in game.players.items():
        if not p.is_alive: continue
        owned_msgs = []
        
        # CCTV
        my_cctvs = [s for s, owner_id in game.cctvs.items() if owner_id == pid]
        if my_cctvs:
            owned_msgs.append(f"📸 [내 CCTV 위치]: {', '.join(my_cctvs)}")
            
        # 덫
        my_traps = [s for s, owner_id in game.traps.items() if owner_id == pid]
        if my_traps:
            owned_msgs.append(f"🪤 [내 덫 위치]: {', '.join(my_traps)}")
            
        # 드론
        my_drones = [d for d in game.drones if d["owner_id"] == pid]
        for d in my_drones:
            owned_msgs.append(f"🛸 [내 드론 위치]: {d['current_station']} ({d['facing_station']} 방면)")
            
        if owned_msgs:
            p.personal_msgs.append("📍 **[설치 아이템 현황]**\n" + "\n".join(owned_msgs))

    await channel.send("\n".join(game.logs))
    
    for p in game.players.values(): p.newly_acquired = []
    # [작업 지시 1] 턴 종료 후 긴급 투표 동시 발의 가능하도록 초기화
    game.is_vote_called_this_turn = False
    game.turn += 1; game.turn_actions = {}
    game.is_processing = False
    await asyncio.sleep(3); await start_subway_turn(channel, game)

async def end_subway(game, winner):
    channel = bot.get_channel(game.cid)
    thief = game.players[game.thief_id]

    if winner == "detective": 
        try: await play_subway_bgm(channel, "gotcha.mp3")
        except: pass
        e = discord.Embed(title="🎊 형사 승리!", description=f"도둑 {thief.member.mention}을 검거했습니다!", color=0x2ECC71)
    elif winner == "thief": 
        try: await play_subway_bgm(channel, "thief.mp3")
        except: pass
        e = discord.Embed(title="🔥 도둑 승리!", description=f"테러에 성공했습니다!", color=0xE74C3C)
    else: 
        try: await play_subway_bgm(channel, "thief.mp3") # 오사도 도둑 승리 판정이므로 thief 재생
        except: pass
        e = discord.Embed(title="💀 도둑 승리 (오사)", description="형사가 동료를 쏴버렸습니다!", color=0xE74C3C)

    await channel.send(embed=e)
    game.is_processing = False
    del subway_games[game.cid]

@bot.command(name="노선도")
async def cmd_subway(ctx):
    if ctx.channel.id in subway_games: await ctx.send("❌ 이미 진행 중입니다."); return
    
    if ctx.author.voice:
        if ctx.voice_client is None: await ctx.author.voice.channel.connect()
        elif ctx.voice_client.channel != ctx.author.voice.channel: await ctx.voice_client.move_to(ctx.author.voice.channel)

    try: 
        await play_sound(ctx, "intro.mp3")
    except Exception as e:
        print(f"BGM 재생 실패: {e}")
    view = SubwayJoinView(ctx.author)
    e = discord.Embed(title="🚇 [지하철 심리 추격전] 모집", description=f"**현재 참가자:** {ctx.author.mention}\n(최소 3명 필요)", color=0x34495E)
    # [이전 Turn 작업 지시 2] 팁 및 종료 안내 문구 추가
    e.add_field(
        name="💡 안내 및 팁",
        value="💡 팁: '강남' 또는 '강남역'처럼 쳐도 모두 정답으로 인정됩니다.\n"
              f"🛑 도저히 모르겠다면 채팅창에 **!노선도종료** 를 입력해서 항복하세요!",
        inline=False
    )
    await ctx.send(embed=e, view=view)

@bot.command(name="노선도종료")
async def cmd_stop_subway(ctx):
    if ctx.channel.id in subway_games: del subway_games[ctx.channel.id]; await ctx.send("🛑 게임을 강제 종료했습니다.")
    else: await ctx.send("❌ 진행 중인 게임이 없습니다.")

@bot.command(name="노선도능력", aliases=["노선도아이템", "지하철능력"])
async def cmd_subway_abilities(ctx):
    embed = discord.Embed(title="🚇 [지하철 심리 추격전] 아이템 도감", color=0x2C3E50)
    
    passive_text = (
        "✅ **천리안**: [2턴마다 자동 발동] 현재 내가 바라보고 있는 정방향 노선 앞쪽 노선에 범인이 있는지 알림.\n\n"
        "✅ **탐지견**: [매 턴 자동 발동] 앞뒤 1칸 내에 범인이 있는지 감지 (Yes/No).\n\n"
        "✅ **통신망**: [매 턴 자동 발동] 무작위 플레이어 1명의 이번 턴 '행동' 파악.\n\n"
        "✅ **노선 스캔망**: [매 턴 자동 발동] 가장 많은 플레이어가 있는 노선 파악.\n\n"
        "✅ **교통카드 내역**: [2턴마다 자동 발동] 현재 위치에 2턴 내에 범인이 지나갔거나 정차했었는지 파악.\n\n"
        "✅ **마이크**: [매 턴 자동 발동] 가장 가까운 사람과의 거리를 숫자로 파악.\n\n"
        "✅ **망원경**: [매 턴 자동 발동] 범인이 나랑 가장 멀리 떨어져 있을 때 알림.\n\n"
        "✅ **폭탄 탐지기**: [매 턴 자동 발동] 내 위치에 폭탄이 있는지 감지(도화선 제외). 형사가 찾으면 획득 후 3턴 뒤 자동 드랍.\n\n"
        "✅ **자전거**: [패시브] 역방향 전환 시 턴 소모 면제. 단, 정방향 이동 시 최대 3칸까지만 가능."
    )
    
    active_text = (
        "✅ **CCTV**: [시작 시 3곳 수동 설치] 범인이 해당 역을 지나가거나 멈추면 본인에게만 알림.\n\n"
        "✅ **폴리스 라인**: [1턴 소모] 게임당 1번 특정 역을 영구 폐쇄하여 누구도 통과 불가하게 만듦.\n\n"
        "✅ **덫**: [시작 시 1곳 설치] 주인을 제외한 플레이어가 밟으면 1턴 휴식, 또한 덫이 포함된 역을 지나치려 하면 그 즉시 정차된다. (밟으면 강제 1턴 휴식하지만, 지나치다 정차할 경우 1턴 쉬지 않음) 덫이 발동되면 즉시 주인의 현재 위치에서 다시 생성됩니다.\n\n"
        "✅ **드론**: [1턴 소모] 지정한 노선에 드론을 출격시켜 1칸씩 자동 왕복. 사람 발견 시 알림.\n\n"
        "✅ **스마트 태그**: [액티브] 같은 역에 멈춘 사람에게 몰래 부착하여 2턴간 실시간 위치 파악."
    )
    
    embed.add_field(name="[자동 발동 및 패시브 🔄]", value=passive_text, inline=False)
    embed.add_field(name="[설치 및 액티브 ⚡]", value=active_text, inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="노선", aliases=["지도", "노선도확인"])
async def cmd_subway_map(ctx):
    # BASE_DIR에 subway_map.png 파일이 있다고 가정
    image_path = os.path.join(BASE_DIR, "subway_map.png")
    
    if os.path.exists(image_path):
        file = discord.File(image_path, filename="subway_map.png")
        embed = discord.Embed(title="🗺️ [지하철 심리 추격전] 노선도", color=0x34495E)
        embed.set_image(url="attachment://subway_map.png")
        embed.set_footer(text="원하는 역의 위치와 환승 노선을 확인하세요!")
        await ctx.send(file=file, embed=embed)
    else:
        await ctx.send("❌ 노선도 이미지 파일(`subway_map.png`)을 찾을 수 없습니다. 봇 폴더에 이미지가 있는지 확인해주세요.")

# ----------------------------------------------------
# 🎮 영웅시장 (Hero Market) 게임 엔진 구현
# ----------------------------------------------------

hero_market_games = {}

async def play_hero_market_bgm(ctx, filename):
    if hasattr(ctx, "response"):  # discord.Interaction
        author = ctx.user
        guild = ctx.guild
    elif hasattr(ctx, "author"):  # commands.Context
        author = ctx.author
        guild = ctx.guild
    elif hasattr(ctx, "guild"):  # TextChannel
        author = None
        guild = ctx.guild
    else:
        return None

    vc = guild.voice_client
    if vc is None or not vc.is_connected():
        if author and getattr(author, "voice", None):
            try:
                vc = await author.voice.channel.connect()
            except Exception as e:
                print(f"음성 채널 연결 실패: {e}")
                return None
        else:
            return None
    elif author and getattr(author, "voice", None) and vc.channel != author.voice.channel:
        try:
            await vc.move_to(author.voice.channel)
        except Exception as e:
            print(f"음성 채널 이동 실패: {e}")

    bgm_dir = os.path.join(BASE_DIR, "영웅시장")
    file_path = os.path.join(bgm_dir, filename)
    if not os.path.exists(file_path):
        file_path = os.path.join(BASE_DIR, filename)
        if not os.path.exists(file_path):
            return None

    if vc.is_playing():
        vc.stop()

    ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg")
    try:
        vc.play(discord.FFmpegPCMAudio(file_path, executable=ffmpeg_path if os.path.exists(ffmpeg_path) else "ffmpeg"))
    except Exception as e:
        print(f"BGM 재생 실패: {e}")
    return vc

class HeroInstance:
    def __init__(self, name, stat, is_hidden=False, min_stat=None, max_stat=None, role=None):
        self.name = name
        self.stat = stat
        self.is_hidden = is_hidden
        self.min_stat = min_stat
        self.max_stat = max_stat
        self.acquired_price = 0  # 구매 가격 (단위: 만 원)
        if role is None:
            self.role = random.choices(['주장', '호위'], weights=[1, 2])[0]
        else:
            self.role = role

class HeroMarketPlayer:
    def __init__(self, member):
        self.member = member
        self.capital = 3000  # 3,000만 원 (단위: 만 원)
        self.locked_funds = 0  # 가압류 금액
        self.heroes = []     # HeroInstance 리스트 (중복 이름 대비)
        self.tournament_captain = None  # 최종전 대장 영웅
        self.tournament_guards = []     # 최종전 호위 영웅 목록

class HeroMarketGame:
    def __init__(self, cid, host, players_list, hero_pool):
        self.cid = cid
        self.host = host
        self.players = {p.id: HeroMarketPlayer(p) for p in players_list}
        self.hero_pool = hero_pool
        self.used_heroes = []
        self.round = 1
        self.total_rounds = len(players_list) * 3
        
        # 25% 확정 더블 라운드 지정
        double_round_count = max(1, round(self.total_rounds * 0.25))
        self.double_rounds = set(random.sample(range(1, self.total_rounds + 1), double_round_count))
        self.double_round_index = 0  # 0: 첫 번째 매물, 1: 두 번째 매물
        self.tie_first_bidder = None  # 동점 상황 시 선착순 1위 백업
        
        self.transaction_logs = []
        
        # 경매 상태
        self.current_hero = None
        self.phase = "lobby"
        self.auction_bids = {}
        self.auction_bid_times = {}
        self.current_highest_bid = 0
        self.current_highest_bidder = None
        self.countdown_seconds = 15
        self.countdown_task = None
        self.countdown_message = None
        
        # 이적시장 상태
        self.turn_votes = set()
        self.proposals = {}
        self.prop_counter = 0
        self.marketplace_message = None
        self.market_items = []

    def draw_hero_name(self):
        if not self.hero_pool:
            if self.used_heroes:
                self.hero_pool = self.used_heroes.copy()
                random.shuffle(self.hero_pool)
                self.used_heroes.clear()
            else:
                self.hero_pool = load_hero_names()
        name = self.hero_pool.pop(0)
        self.used_heroes.append(name)
        return name

    def generate_hero(self):
        name = self.draw_hero_name()
        is_hidden = random.random() < 0.10
        if is_hidden:
            min_val = random.randint(1, 60)
            max_val = random.randint(min_val + 20, 100)
            max_val = min(max_val, 100)
            stat = random.randint(min_val, max_val)
            return HeroInstance(name, stat, is_hidden=True, min_stat=min_val, max_stat=max_val)
        else:
            stat = random.randint(1, 100)
            return HeroInstance(name, stat, is_hidden=False)

def load_hero_names():
    path = os.path.join(BASE_DIR, "HeroName.txt")
    names = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                names = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Error loading HeroName.txt: {e}")
    names = list(dict.fromkeys(names))
    if not names:
        names = ["세종대왕", "이순신", "김유신", "광개토대왕", "장보고", 
                 "강감찬", "을지문덕", "대조영", "계백", "곽재우"]
    random.shuffle(names)
    return names

def find_player_by_name(game, name_input):
    import re
    clean_input = name_input.strip()
    mention_match = re.match(r'<@!?(\d+)>', clean_input)
    if mention_match:
        pid = int(mention_match.group(1))
        if pid in game.players:
            return game.players[pid]
            
    clean_lower = clean_input.lower().replace(" ", "")
    for pid, p in game.players.items():
        p_name = p.member.name.lower().replace(" ", "")
        p_disp = p.member.display_name.lower().replace(" ", "")
        if p_name == clean_lower or p_disp == clean_lower:
            return p
            
    for pid, p in game.players.items():
        if clean_lower in p.member.name.lower().replace(" ", "") or clean_lower in p.member.display_name.lower().replace(" ", ""):
            return p
    return None

def find_owned_hero(player, hero_name_input):
    clean_input = hero_name_input.strip().lower().replace(" ", "")
    for h_inst in player.heroes:
        if h_inst.name.lower().replace(" ", "") == clean_input:
            return h_inst
    return None

# --- [1단계 경매 진행] ---
async def start_auction_round(channel, game):
    game.phase = "auction_step1"
    game.current_hero = game.generate_hero()
    game.auction_bids.clear()
    game.auction_bid_times.clear()
    game.current_highest_bid = 0
    game.current_highest_bidder = None
    
    if game.round in game.double_rounds and game.double_round_index == 0:
        await channel.send("🎉 **[돌발 이벤트] 이번 라운드는 더블 매물 라운드입니다! 2명의 영웅이 순차적으로 경매에 등장합니다!**")
        
    title_str = f"⚔️ [영웅문] 경매 개시 - 라운드 {game.round}/{game.total_rounds}"
    if game.round in game.double_rounds:
        title_str += f" (더블 {game.double_round_index + 1}번째 매물)"
        
    embed = discord.Embed(
        title=title_str,
        color=0xE74C3C
    )
    if game.current_hero.is_hidden:
        hero_desc = f"**[{game.current_hero.role}] {game.current_hero.name}** <?? : {game.current_hero.min_stat}~{game.current_hero.max_stat}> (히든 영웅)"
    else:
        hero_desc = f"**[{game.current_hero.role}] {game.current_hero.name}** <스탯: {game.current_hero.stat}>"
        
    embed.add_field(name="경매 대상 영웅", value=hero_desc, inline=False)
    embed.add_field(
        name="경매 안내",
        value="1단계 기본 입찰: 아래 버튼을 눌러 첫 입찰가를 제출하거나 입찰을 포기하세요.\n(최소 입찰가: 100만 원, 초기 자본: 3,000만 원)",
        inline=False
    )
    
    status_lines = []
    for pid, p in game.players.items():
        status_lines.append(f"• {p.member.display_name}: 대기 중 ⏳")
    embed.add_field(name="참가자 입찰 현황", value="\n".join(status_lines), inline=False)
    
    view = HeroMarketAuctionView(game)
    msg = await channel.send(embed=embed, view=view)
    game.countdown_message = msg

class HeroMarketAuctionView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="💰 입찰하기", style=discord.ButtonStyle.green)
    async def bid(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players:
            await interaction.response.send_message("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
        if interaction.user.id in self.game.auction_bids:
            await interaction.response.send_message("❌ 이미 입찰(또는 포기)을 완료하셨습니다.", ephemeral=True)
            return
        modal = HeroMarketBidModal(self.game, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🏳️ 입찰 포기", style=discord.ButtonStyle.red)
    async def give_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players:
            await interaction.response.send_message("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
        if interaction.user.id in self.game.auction_bids:
            await interaction.response.send_message("❌ 이미 입찰(또는 포기)을 완료하셨습니다.", ephemeral=True)
            return
            
        self.game.auction_bids[interaction.user.id] = 0
        self.game.auction_bid_times[interaction.user.id] = time.time()
        
        await interaction.response.send_message("🏳️ 입찰을 포기하셨습니다. (0원 처리)", ephemeral=True)
        await self.update_auction_status(interaction)

    async def update_auction_status(self, interaction: discord.Interaction):
        embed = interaction.message.embeds[0]
        status_lines = []
        for pid, p in self.game.players.items():
            if pid in self.game.auction_bids:
                bid = self.game.auction_bids[pid]
                if bid == 0:
                    status_lines.append(f"• {p.member.display_name}: 🏳️ 입찰 포기")
                else:
                    status_lines.append(f"• {p.member.display_name}: ✅ 입찰 완료")
            else:
                status_lines.append(f"• {p.member.display_name}: 대기 중 ⏳")
                
        embed.set_field_at(2, name="참가자 입찰 현황", value="\n".join(status_lines), inline=False)
        await interaction.message.edit(embed=embed, view=self)
        
        if len(self.game.auction_bids) == len(self.game.players):
            self.stop()
            await process_step1_results(interaction.channel, self.game)

class HeroMarketBidModal(discord.ui.Modal):
    def __init__(self, game, view):
        super().__init__(title="영웅문 경매 입찰")
        self.game = game
        self.view = view
        
        self.bid_input = discord.ui.TextInput(
            label="입찰가 입력 (단위: 만 원)",
            placeholder="예: 100 (100만 원)",
            min_length=1,
            max_length=10
        )
        self.add_item(self.bid_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        player = self.game.players.get(user_id)
        if not player:
            return
            
        val_str = self.bid_input.value.strip()
        try:
            for char in ["만", "원", ",", " "]:
                val_str = val_str.replace(char, "")
            bid_amount = int(val_str)
        except ValueError:
            await interaction.followup.send("❌ 올바른 숫자를 입력해주세요. (예: 150 또는 150만 원)", ephemeral=True)
            return
            
        if bid_amount < 100:
            await interaction.followup.send("❌ 최소 입찰가는 100만 원입니다.", ephemeral=True)
            return
            
        if bid_amount % 100 != 0:
            await interaction.followup.send("❌ 입찰가는 반드시 100만 원 단위여야 합니다. (예: 100, 500, 1200)", ephemeral=True)
            return
            
        # 보유 한도 체크
        if len(player.heroes) >= 4:
            await interaction.followup.send("❌ 영웅 보유 한도(최대 4명)가 꽉 찼습니다! 이적시장에서 방출하여 슬롯을 비워야 입찰 가능합니다.", ephemeral=True)
            return

        available = player.capital - player.locked_funds
        if bid_amount > available:
            await interaction.followup.send(f"❌ 잔액이 부족합니다. (사용 가능 잔액: {available}만 원)", ephemeral=True)
            return
            
        player.locked_funds = bid_amount
        self.game.auction_bids[user_id] = bid_amount
        self.game.auction_bid_times[user_id] = time.time()
        
        await interaction.followup.send(f"✅ {bid_amount}만 원 입찰 완료!", ephemeral=True)
        await self.view.update_auction_status(interaction)

async def process_step1_results(channel, game):
    valid_bids = {pid: bid for pid, bid in game.auction_bids.items() if bid > 0}
    
    if not valid_bids:
        for p in game.players.values():
            p.locked_funds = 0
            
        embed = discord.Embed(
            title="💨 경매 유찰",
            description=f"모든 플레이어가 입찰을 포기하여 이번 경매(**[{game.current_hero.role}] {game.current_hero.name}**)는 유찰되었습니다.",
            color=0x7F8C8D
        )
        await channel.send(embed=embed)
        await asyncio.sleep(2)
        if game.round in game.double_rounds and game.double_round_index == 0:
            game.double_round_index = 1
            await start_auction_round(channel, game)
        else:
            game.double_round_index = 0
            await start_marketplace_phase(channel, game)
        return

    max_bid = max(valid_bids.values())
    highest_bidders = [pid for pid, bid in valid_bids.items() if bid == max_bid]
    hero = game.current_hero

    if len(valid_bids) == 1:
        winner_id = highest_bidders[0]
        winner_player = game.players[winner_id]
        
        winner_player.capital -= max_bid
        winner_player.locked_funds = 0
        hero.acquired_price = max_bid
        winner_player.heroes.append(hero)
        
        for pid, p in game.players.items():
            if pid != winner_id:
                p.locked_funds = 0
                
        embed = discord.Embed(
            title="🏆 [단독 입찰] 즉시 낙찰!",
            description=f"단 한 명만 입찰에 참여하여 **[{hero.role}] {hero.name}**이(가) 즉시 낙찰되었습니다.",
            color=0xF1C40F
        )
        if hero.is_hidden:
            hero_info = f"**[{hero.role}] {hero.name}** <실제 스탯: **{hero.stat}**> (히든 공개!)"
        else:
            hero_info = f"**[{hero.role}] {hero.name}** <스탯: **{hero.stat}**>"
            
        embed.add_field(name="낙찰 영웅", value=hero_info, inline=False)
        embed.add_field(name="최종 낙찰자", value=winner_player.member.mention, inline=True)
        embed.add_field(name="낙찰 금액", value=f"💰 **{max_bid}만 원**", inline=True)
        embed.add_field(name="남은 자본", value=f"{winner_player.capital}만 원", inline=True)
        await channel.send(embed=embed)
        
        stat_reveal = f"{hero.stat}"
        game.transaction_logs.append(
            f"🏆 [단독 낙찰] {winner_player.member.display_name} ➔ [{hero.role}] {hero.name} (스탯: {stat_reveal}, {max_bid}만 원)"
        )
        await asyncio.sleep(3)
        if game.round in game.double_rounds and game.double_round_index == 0:
            game.double_round_index = 1
            await start_auction_round(channel, game)
        else:
            game.double_round_index = 0
            await start_marketplace_phase(channel, game)
        return

    game.phase = "auction_step2"
    game.countdown_seconds = 15

    if len(highest_bidders) >= 2:
        for pid, p in game.players.items():
            if pid not in highest_bidders:
                p.locked_funds = 0
                
        highest_bidders.sort(key=lambda pid: game.auction_bid_times.get(pid, 9999999999.0))
        
        game.current_highest_bid = max_bid
        game.current_highest_bidder = None
        game.tie_first_bidder = highest_bidders[0]
        
        await channel.send(f"⚠️ **{max_bid}만 원** 입찰자가 여러 명입니다! 15초간 마지막 재입찰을 진행합니다.")
        
        embed = discord.Embed(
            title="⚡ 경매 2단계 - 추가 경쟁 페이즈",
            description="최고 입찰가가 공개되었습니다! 15초 내에 더 높은 금액을 부르면 타이머가 15초로 즉시 리셋됩니다.",
            color=0xE67E22
        )
        if hero.is_hidden:
            hero_desc = f"**[{hero.role}] {hero.name}** <?? : {hero.min_stat}~{hero.max_stat}>"
        else:
            hero_desc = f"**[{hero.role}] {hero.name}** <스탯: {hero.stat}>"
            
        embed.add_field(name="경매 대상 영웅", value=hero_desc, inline=False)
        embed.add_field(name="현재 최고가", value=f"💰 **{max_bid}만 원** (공동 최고가 - 동점자 발생)", inline=False)
    else:
        winner_id = highest_bidders[0]
        game.current_highest_bid = max_bid
        game.current_highest_bidder = winner_id
        
        for pid, p in game.players.items():
            if pid != winner_id:
                p.locked_funds = 0
                
        winner_player = game.players[winner_id]
        
        embed = discord.Embed(
            title="⚡ 경매 2단계 - 추가 경쟁 페이즈",
            description="최고 입찰가가 공개되었습니다! 15초 내에 더 높은 금액을 부르면 타이머가 15초로 즉시 리셋됩니다.",
            color=0xE67E22
        )
        if hero.is_hidden:
            hero_desc = f"**[{hero.role}] {hero.name}** <?? : {hero.min_stat}~{hero.max_stat}>"
        else:
            hero_desc = f"**[{hero.role}] {hero.name}** <스탯: {hero.stat}>"
            
        embed.add_field(name="경매 대상 영웅", value=hero_desc, inline=False)
        embed.add_field(name="현재 최고가", value=f"💰 **{max_bid}만 원** ({winner_player.member.mention})", inline=False)
        
    embed.add_field(name="남은 시간", value="⏰ **15초**", inline=False)
    
    view = HeroMarketCountdownView(game)
    msg = await channel.send(embed=embed, view=view)
    game.countdown_message = msg
    
    if game.countdown_task:
        game.countdown_task.cancel()
    game.countdown_task = asyncio.create_task(run_countdown(channel, game))

# --- [2단계 카운트다운 루프] ---
async def run_countdown(channel, game):
    try:
        while game.countdown_seconds > 0:
            await asyncio.sleep(1)
            game.countdown_seconds -= 1
            if game.countdown_seconds in [10, 5, 3, 2, 1] or (game.countdown_seconds % 3 == 0):
                await update_countdown_message(game)
        await finalize_auction(channel, game)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Error in countdown loop: {e}")

async def update_countdown_message(game):
    if not game.countdown_message:
        return
    try:
        embed = game.countdown_message.embeds[0]
        if game.current_highest_bidder is not None:
            winner_member = game.players[game.current_highest_bidder].member
            bidder_text = winner_member.mention
        else:
            bidder_text = "공동 최고가 - 동점자 발생"
        embed.set_field_at(1, name="현재 최고가", value=f"💰 **{game.current_highest_bid}만 원** ({bidder_text})", inline=False)
        embed.set_field_at(2, name="남은 시간", value=f"⏰ **{game.countdown_seconds}초**", inline=False)
        await game.countdown_message.edit(embed=embed)
    except Exception as e:
        print(f"Error updating countdown: {e}")

class HeroMarketCountdownView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="⚡ 추가 입찰하기", style=discord.ButtonStyle.primary)
    async def bid(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players:
            await interaction.response.send_message("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
        if self.game.current_highest_bidder is not None and interaction.user.id == self.game.current_highest_bidder:
            await interaction.response.send_message("❌ 귀하는 이미 현재 최고 입찰자입니다.", ephemeral=True)
            return
        modal = HeroMarketCountdownBidModal(self.game, self)
        await interaction.response.send_modal(modal)

class HeroMarketCountdownBidModal(discord.ui.Modal):
    def __init__(self, game, view):
        super().__init__(title="추가 경쟁 입찰")
        self.game = game
        self.view = view
        
        self.bid_input = discord.ui.TextInput(
            label=f"입찰가 (현재 최고가: {game.current_highest_bid}만 원)",
            placeholder="예: 1600 (1600만 원)",
            min_length=1,
            max_length=10
        )
        self.add_item(self.bid_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        player = self.game.players.get(user_id)
        if not player:
            return
            
        val_str = self.bid_input.value.strip()
        try:
            for char in ["만", "원", ",", " "]:
                val_str = val_str.replace(char, "")
            new_bid = int(val_str)
        except ValueError:
            await interaction.followup.send("❌ 올바른 숫자를 입력해주세요.", ephemeral=True)
            return
            
        if new_bid % 100 != 0:
            await interaction.followup.send("❌ 입찰가는 반드시 100만 원 단위여야 합니다. (예: 100, 500, 1200)", ephemeral=True)
            return
            
        # 보유 한도 체크
        if len(player.heroes) >= 4:
            await interaction.followup.send("❌ 영웅 보유 한도(최대 4명)가 꽉 찼습니다! 이적시장에서 방출하여 슬롯을 비워야 입찰 가능합니다.", ephemeral=True)
            return

        available = player.capital - player.locked_funds
        if new_bid > available:
            await interaction.followup.send(f"❌ 잔액이 부족합니다. (사용 가능 잔액: {available}만 원)", ephemeral=True)
            return
            
        if new_bid > self.game.current_highest_bid:
            if self.game.current_highest_bidder is not None:
                prev_bidder = self.game.current_highest_bidder
                if prev_bidder in self.game.players:
                    self.game.players[prev_bidder].locked_funds = 0
            else:
                for pid, p in self.game.players.items():
                    if p.locked_funds == self.game.current_highest_bid:
                        p.locked_funds = 0
                
            player.locked_funds = new_bid
            
            # 4단계: 변수 업데이트
            self.game.current_highest_bid = new_bid
            self.game.current_highest_bidder = user_id
            self.game.countdown_seconds = 15
        else:
            await interaction.followup.send(f"❌ 현재 최고가({self.game.current_highest_bid}만 원)보다 높은 금액을 불러야 합니다.", ephemeral=True)
            return
            
        await interaction.channel.send(f"📣 {interaction.user.mention}님이 **{new_bid}만 원**으로 입찰했습니다! (15초 리셋)")
        
        if self.game.countdown_task:
            self.game.countdown_task.cancel()
        self.game.countdown_task = asyncio.create_task(run_countdown(interaction.channel, self.game))
        
        await interaction.followup.send(f"✅ {new_bid}만 원 입찰 성공!", ephemeral=True)
        await update_countdown_message(self.game)

async def finalize_auction(channel, game):
    game.phase = "marketplace"
    
    winner_id = game.current_highest_bidder
    if winner_id is None:
        winner_id = game.tie_first_bidder
    winner_player = game.players[winner_id]
    final_price = game.current_highest_bid
    hero = game.current_hero
    
    winner_player.capital -= final_price
    winner_player.locked_funds = 0
    
    for pid, p in game.players.items():
        if pid != winner_id:
            p.locked_funds = 0
            
    hero.acquired_price = final_price
    winner_player.heroes.append(hero)
    
    embed = discord.Embed(
        title="🏆 경매 낙찰 완료!",
        color=0x2ECC71
    )
    if hero.is_hidden:
        hero_info = f"**[{hero.role}] {hero.name}** <실제 스탯: **{hero.stat}**> (히든 공개!)"
    else:
        hero_info = f"**[{hero.role}] {hero.name}** <스탯: **{hero.stat}**>"
        
    embed.add_field(name="낙찰 영웅", value=hero_info, inline=False)
    embed.add_field(name="최종 낙찰자", value=winner_player.member.mention, inline=True)
    embed.add_field(name="낙찰 가격", value=f"💰 **{final_price}만 원**", inline=True)
    embed.add_field(name="남은 자본", value=f"{winner_player.capital}만 원", inline=True)
    await channel.send(embed=embed)
    
    stat_reveal = f"{hero.stat}"
    game.transaction_logs.append(
        f"🏆 [경매 낙찰] {winner_player.member.display_name} ➔ [{hero.role}] {hero.name} (스탯: {stat_reveal}, {final_price}만 원)"
    )
    
    await asyncio.sleep(3)
    if game.round in game.double_rounds and game.double_round_index == 0:
        game.double_round_index = 1
        await start_auction_round(channel, game)
    else:
        game.double_round_index = 0
        await start_marketplace_phase(channel, game)

# --- [이적시장 페이즈] ---
async def start_marketplace_phase(channel, game):
    game.phase = "marketplace"
    game.turn_votes.clear()
    
    embed = build_marketplace_embed(game)
    view = HeroMarketplaceView(game)
    msg = await channel.send(embed=embed, view=view)
    game.marketplace_message = msg

def build_marketplace_embed(game):
    embed = discord.Embed(
        title=f"🏪 이적시장 오픈! - 라운드 {game.round}/{game.total_rounds}",
        description="이적시장이 열렸습니다. 플레이어들 간의 거래(판매, 구매, 트레이드), 영웅 방출을 진행할 수 있습니다.\n"
                    "모든 유저가 완료했거나 과반수가 찬성하면 다음 라운드로 넘어갑니다.",
        color=0x9B59B6
    )
    for pid, p in game.players.items():
        hero_list = [f"[{h.role}] {h.name}({h.stat})" for h in p.heroes]
        heroes_str = ", ".join(hero_list) if hero_list else "보유 영웅 없음"
        embed.add_field(
            name=f"👤 {p.member.display_name}",
            value=f"• 자본: **{p.capital}만 원**\n• 영웅 ({len(p.heroes)}/4명): {heroes_str}",
            inline=False
        )
    embed.set_footer(text=f"턴 종료 투표 완료: {len(game.turn_votes)} / {len(game.players)}명")
    return embed

async def update_marketplace_main_message(channel, game):
    if not game.marketplace_message:
        return
    try:
        embed = build_marketplace_embed(game)
        await game.marketplace_message.edit(embed=embed)
    except Exception as e:
        print(f"Error updating marketplace main: {e}")

class HeroMarketplaceView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="💵 판매", style=discord.ButtonStyle.green)
    async def sell(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players:
            await interaction.response.send_message("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
        player = self.game.players[interaction.user.id]
        if not player.heroes:
            await interaction.response.send_message("❌ 판매할 영웅이 없습니다.", ephemeral=True)
            return
        view = HeroMarketSellSelectView(self.game, player)
        await interaction.response.send_message("🔽 판매할 영웅을 선택하세요.", view=view, ephemeral=True)

    @discord.ui.button(label="🔍 구매 (비밀제안)", style=discord.ButtonStyle.primary)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players:
            await interaction.response.send_message("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
        player = self.game.players[interaction.user.id]
        if len(player.heroes) >= 4:
            await interaction.response.send_message("❌ 본인의 영웅 보유 한도(최대 4명)가 꽉 차서 구매 제안을 보낼 수 없습니다.", ephemeral=True)
            return
        view = HeroMarketBuyFlowView(self.game, player)
        await interaction.response.send_message("🔍 **[구매 제안]** 아래 드롭다운에서 구매 제안할 대상을 선택하세요.", view=view, ephemeral=True)

    @discord.ui.button(label="🤝 트레이드", style=discord.ButtonStyle.secondary)
    async def trade(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players:
            await interaction.response.send_message("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
        player = self.game.players[interaction.user.id]
        if not player.heroes:
            await interaction.response.send_message("❌ 본인이 보유한 영웅이 없어 트레이드가 불가능합니다.", ephemeral=True)
            return
        view = HeroMarketTradeFlowView(self.game, player)
        await interaction.response.send_message("🤝 **[트레이드 제안]** 아래 드롭다운에서 상대방을 선택하세요.", view=view, ephemeral=True)

    @discord.ui.button(label="🧹 영웅 방출", style=discord.ButtonStyle.danger)
    async def release(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.game.players:
            await interaction.response.send_message("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
        player = self.game.players[interaction.user.id]
        if not player.heroes:
            await interaction.response.send_message("❌ 방출할 영웅이 없습니다.", ephemeral=True)
            return
        view = HeroMarketReleaseSelectView(self.game, player)
        await interaction.response.send_message("🧹 **[영웅 방출]** 아래 드롭다운에서 방출할 영웅을 선택하세요.", view=view, ephemeral=True)

    @discord.ui.button(label="🗳️ 턴 종료", style=discord.ButtonStyle.red)
    async def vote_end(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id not in self.game.players:
            return
        if user_id in self.game.turn_votes:
            await interaction.response.send_message("❌ 이미 투표하셨습니다.", ephemeral=True)
            return
            
        self.game.turn_votes.add(user_id)
        majority = len(self.game.players)
        
        await interaction.response.send_message(f"🗳️ 턴 종료 투표 완료! (현재 {len(self.game.turn_votes)}/{majority}명)", ephemeral=True)
        
        if len(self.game.turn_votes) >= majority:
            self.stop()
            try:
                await interaction.message.edit(content="🗳️ 모든 인원 동의로 이적시장이 종료됩니다.", view=None)
            except:
                pass
            await next_round(interaction.channel, self.game)
        else:
            try:
                embed = build_marketplace_embed(self.game)
                await interaction.message.edit(embed=embed)
            except:
                pass

# --- [거래 모달 정의] ---
class HeroMarketOpenSellView(discord.ui.View):
    def __init__(self, game, seller_id, hero_name, price):
        super().__init__(timeout=None)
        self.game = game
        self.seller_id = seller_id
        self.hero_name = hero_name
        self.price = price

    @discord.ui.button(label="🛒 즉시 구매", style=discord.ButtonStyle.success)
    async def buy_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        buyer_id = interaction.user.id
        if buyer_id not in self.game.players:
            await interaction.followup.send("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
            
        if self.seller_id == buyer_id:
            await interaction.followup.send("❌ 자신의 영웅은 구매할 수 없습니다.", ephemeral=True)
            return
            
        buyer = self.game.players[buyer_id]
        if len(buyer.heroes) >= 4:
            await interaction.followup.send("❌ 영웅 보유 한도(최대 4명)가 꽉 찼습니다.", ephemeral=True)
            return
            
        available = buyer.capital - buyer.locked_funds
        if available < self.price:
            await interaction.followup.send("❌ 잔액이 부족합니다.", ephemeral=True)
            return
            
        seller = self.game.players.get(self.seller_id)
        if not seller:
            await interaction.followup.send("❌ 판매자 정보를 찾을 수 없습니다.", ephemeral=True)
            return
            
        hero_inst = find_owned_hero(seller, self.hero_name)
        if not hero_inst:
            await interaction.followup.send("❌ 판매자가 이미 영웅을 방출했거나 다른 곳에 팔았습니다.", ephemeral=True)
            self.stop()
            try:
                await interaction.message.edit(content="❌ 판매 종료 (영웅이 판매자의 인벤토리에 없습니다)", view=None)
            except:
                pass
            return
            
        # 거래 체결
        seller.heroes.remove(hero_inst)
        hero_inst.acquired_price = self.price
        buyer.heroes.append(hero_inst)
        
        buyer.capital -= self.price
        seller.capital += self.price
        
        # 시장 매물 리스트에서 제거
        for item in list(self.game.market_items):
            if item.get("seller_id") == self.seller_id and item.get("hero").name == self.hero_name:
                self.game.market_items.remove(item)
                break
        
        self.game.transaction_logs.append(
            f"🤝 [공개 거래] {seller.member.display_name} ➔ {buyer.member.display_name} ({self.hero_name}, {self.price}만 원)"
        )
        
        self.stop()
        try:
            await interaction.message.edit(
                content=f"🤝 거래 완료! {interaction.user.mention}님이 **{self.price}만 원**에 구매했습니다.",
                view=None
            )
        except Exception as e:
            print(f"Error editing sell view msg: {e}")
            
        await interaction.followup.send(f"✅ [{self.hero_name}] 영웅을 {self.price}만 원에 즉시 구매하였습니다!", ephemeral=True)
        await update_marketplace_main_message(interaction.channel, self.game)

class HeroMarketSellSelectView(discord.ui.View):
    def __init__(self, game, player):
        super().__init__(timeout=60.0)
        self.game = game
        self.player = player
        
        options = []
        for idx, h in enumerate(player.heroes):
            options.append(discord.SelectOption(
                label=f"[{h.role}] {h.name} (스탯: {h.stat})",
                value=str(idx)
            ))
            
        self.select = discord.ui.Select(
            placeholder="판매할 영웅을 선택하세요.",
            min_values=1,
            max_values=1,
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
    async def select_callback(self, interaction: discord.Interaction):
        idx = int(self.select.values[0])
        if idx >= len(self.player.heroes):
            await interaction.response.send_message("❌ 영웅 정보가 올바르지 않습니다.", ephemeral=True)
            return
            
        hero = self.player.heroes[idx]
        modal = HeroMarketSellPriceModal(self.game, hero)
        await interaction.response.send_modal(modal)

class HeroMarketSellPriceModal(discord.ui.Modal):
    def __init__(self, game, hero):
        super().__init__(title=f"[{hero.name}] 판매 가격 입력")
        self.game = game
        self.hero = hero
        
        self.price = discord.ui.TextInput(
            label="판매 가격 (단위: 만 원)",
            placeholder="예: 1500 (1500만 원)",
            min_length=1,
            max_length=10
        )
        self.add_item(self.price)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        proposer_id = interaction.user.id
        proposer = self.game.players[proposer_id]
        
        if self.hero not in proposer.heroes:
            await interaction.followup.send("❌ 보유하고 있지 않은 영웅입니다.", ephemeral=True)
            return
            
        price_val = self.price.value
        try:
            for char in ["만", "원", ",", " "]:
                price_val = price_val.replace(char, "")
            price = int(price_val)
        except ValueError:
            await interaction.followup.send("❌ 올바른 숫자를 입력해주세요.", ephemeral=True)
            return
            
        if price <= 0:
            await interaction.followup.send("❌ 가격은 0보다 커야 합니다.", ephemeral=True)
            return
            
        if price % 100 != 0:
            await interaction.followup.send("❌ 거래 및 제안 금액은 반드시 100만 원 단위여야 합니다. (1만 원, 10만 원 단위 꼼수 불가)", ephemeral=True)
            return
            
        view = HeroMarketOpenSellView(self.game, proposer_id, self.hero.name, price)
        await interaction.channel.send(
            content=f"📢 [공개 판매] {interaction.user.mention}님이 **[[{self.hero.role}] {self.hero.name}]**을(를) **{price}만 원**에 시장에 내놓았습니다! (선착순)",
            view=view
        )
        
        # 시장 매물 리스트에 등록
        item = {
            "seller_id": proposer_id,
            "hero": self.hero,
            "price": price,
            "view": view
        }
        self.game.market_items.append(item)
        
        await interaction.followup.send("✅ 성공적으로 시장에 등록했습니다.", ephemeral=True)


class HeroMarketReleaseSelectView(discord.ui.View):
    def __init__(self, game, player):
        super().__init__(timeout=60.0)
        self.game = game
        self.player = player
        
        options = []
        for idx, h in enumerate(player.heroes):
            options.append(discord.SelectOption(
                label=f"[{h.role}] {h.name} (스탯: {h.stat})",
                value=str(idx)
            ))
            
        self.select = discord.ui.Select(
            placeholder="방출할 영웅을 선택하세요.",
            min_values=1,
            max_values=1,
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        idx = int(self.select.values[0])
        if idx >= len(self.player.heroes):
            await interaction.followup.send("❌ 영웅 정보가 올바르지 않습니다.", ephemeral=True)
            return
            
        hero = self.player.heroes[idx]
        refund = hero.stat * 5  # 기본가(stat * 10만 원)의 반값
        
        self.player.heroes.remove(hero)
        self.player.capital += refund
        
        # 시장 매물 리스트에서 제거
        for item in list(self.game.market_items):
            if item.get("seller_id") == interaction.user.id and item.get("hero").name == hero.name:
                self.game.market_items.remove(item)
                break
                
        stat_reveal = f"{hero.stat}"
        await interaction.channel.send(
            f"🧹 **방출 알림**\n{interaction.user.mention}님이 **[[{hero.role}] {hero.name} <스탯: {stat_reveal}>]**을 방출하였습니다.\n"
            f"기본가({hero.stat * 10}만 원)의 반값인 **{refund}만 원**이 환급되었습니다. (남은 잔액: {self.player.capital}만 원)"
        )
        
        self.game.transaction_logs.append(
            f"🧹 [방출] {self.player.member.display_name} ➔ [{hero.role}] {hero.name} (스탯: {stat_reveal}, 환급: {refund}만 원)"
        )
        
        self.clear_items()
        await interaction.edit_original_response(content=f"✅ [{hero.name}]을 방출하고 {refund}만 원을 환급받았습니다.", view=None)
        await update_marketplace_main_message(interaction.channel, self.game)

class HeroMarketBuyFlowView(discord.ui.View):
    def __init__(self, game, proposer):
        super().__init__(timeout=120.0)
        self.game = game
        self.proposer = proposer
        self.target = None
        self.selected_hero = None
        
        # 1단계: 상대 플레이어 선택 드롭다운
        other_players = [p for pid, p in game.players.items() if pid != proposer.member.id]
        options = []
        for p in other_players:
            options.append(discord.SelectOption(
                label=p.member.display_name,
                value=str(p.member.id)
            ))
            
        if not options:
            self.add_item(discord.ui.Button(label="상대 플레이어가 없습니다.", disabled=True))
            return
            
        self.select_target = discord.ui.Select(
            placeholder="구매 제안을 보낼 대상을 선택하세요.",
            min_values=1,
            max_values=1,
            options=options
        )
        self.select_target.callback = self.select_target_callback
        self.add_item(self.select_target)
        
    async def select_target_callback(self, interaction: discord.Interaction):
        target_id = int(self.select_target.values[0])
        self.target = self.game.players.get(target_id)
        if not self.target:
            await interaction.response.send_message("❌ 상대방을 찾을 수 없습니다.", ephemeral=True)
            return
            
        if not self.target.heroes:
            await interaction.response.send_message("❌ 해당 플레이어는 보유한 영웅이 없습니다.", ephemeral=True)
            return
            
        # 2단계: 상대방 영웅 선택 드롭다운으로 갱신
        self.clear_items()
        
        options = []
        for idx, h in enumerate(self.target.heroes):
            options.append(discord.SelectOption(
                label=f"[{h.role}] {h.name} (스탯: {h.stat})",
                value=str(idx)
            ))
            
        self.select_hero = discord.ui.Select(
            placeholder=f"{self.target.member.display_name}님의 영웅을 선택하세요.",
            min_values=1,
            max_values=1,
            options=options
        )
        self.select_hero.callback = self.select_hero_callback
        self.add_item(self.select_hero)
        
        await interaction.response.edit_message(
            content=f"🔽 **[2단계]** {self.target.member.mention}님의 영웅을 선택하세요.",
            view=self
        )
        
    async def select_hero_callback(self, interaction: discord.Interaction):
        idx = int(self.select_hero.values[0])
        if idx >= len(self.target.heroes):
            await interaction.response.send_message("❌ 영웅 정보가 올바르지 않습니다.", ephemeral=True)
            return
            
        self.selected_hero = self.target.heroes[idx]
        
        # 3단계: 가격 입력 모달 띄우기
        modal = HeroMarketBuyPriceModal(self.game, self.proposer, self.target, self.selected_hero)
        await interaction.response.send_modal(modal)

class HeroMarketBuyPriceModal(discord.ui.Modal):
    def __init__(self, game, proposer, target, hero):
        super().__init__(title=f"[{hero.name}] 구매 가격 제안")
        self.game = game
        self.proposer = proposer
        self.target = target
        self.hero = hero
        
        self.price = discord.ui.TextInput(
            label="제안 가격 (단위: 만 원)",
            placeholder="예: 2000 (2000만 원)",
            min_length=1,
            max_length=10
        )
        self.add_item(self.price)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if len(self.proposer.heroes) >= 4:
            await interaction.followup.send("❌ 본인의 영웅 보유 한도(최대 4명)가 꽉 차서 구매 제안을 보낼 수 없습니다.", ephemeral=True)
            return
            
        if self.hero not in self.target.heroes:
            await interaction.followup.send("❌ 상대방이 해당 영웅을 보유하고 있지 않습니다.", ephemeral=True)
            return
            
        price_val = self.price.value
        try:
            for char in ["만", "원", ",", " "]:
                price_val = price_val.replace(char, "")
            price = int(price_val)
        except ValueError:
            await interaction.followup.send("❌ 올바른 숫자를 입력해주세요.", ephemeral=True)
            return
            
        if price <= 0:
            await interaction.followup.send("❌ 가격은 0보다 커야 합니다.", ephemeral=True)
            return
            
        if price % 100 != 0:
            await interaction.followup.send("❌ 거래 및 제안 금액은 반드시 100만 원 단위여야 합니다. (1만 원, 10만 원 단위 꼼수 불가)", ephemeral=True)
            return
            
        if self.proposer.capital < price:
            await interaction.followup.send(f"❌ 본인의 잔액이 부족합니다. (내 잔액: {self.proposer.capital}만 원)", ephemeral=True)
            return
            
        self.game.prop_counter += 1
        prop_id = f"buy_{self.game.prop_counter}"
        
        proposal = {
            "id": prop_id,
            "type": "buy",
            "proposer_id": self.proposer.member.id,
            "target_id": self.target.member.id,
            "hero_name": self.hero.name,
            "price": price,
            "status": "pending"
        }
        self.game.proposals[prop_id] = proposal
        
        view = HeroMarketProposalView(self.game, prop_id)
        msg = await interaction.channel.send(
            content=f"📬 {self.target.member.mention}님, {interaction.user.mention}님이 **[비밀 구매 제안]**을 보냈습니다. 아래 버튼을 눌러 확인하세요.",
            view=view
        )
        proposal["msg_id"] = msg.id
        await interaction.followup.send("✅ 구매 제안이 성공적으로 발송되었습니다.", ephemeral=True)

class HeroMarketTradeFlowView(discord.ui.View):
    def __init__(self, game, proposer):
        super().__init__(timeout=120.0)
        self.game = game
        self.proposer = proposer
        self.target = None
        self.my_hero = None
        self.target_hero = None
        
        # 1단계: 상대 플레이어 선택 드롭다운
        other_players = [p for pid, p in game.players.items() if pid != proposer.member.id]
        options = []
        for p in other_players:
            options.append(discord.SelectOption(
                label=p.member.display_name,
                value=str(p.member.id)
            ))
            
        if not options:
            self.add_item(discord.ui.Button(label="상대 플레이어가 없습니다.", disabled=True))
            return
            
        self.select_target = discord.ui.Select(
            placeholder="트레이드 제안을 보낼 대상을 선택하세요.",
            min_values=1,
            max_values=1,
            options=options
        )
        self.select_target.callback = self.select_target_callback
        self.add_item(self.select_target)
        
    async def select_target_callback(self, interaction: discord.Interaction):
        target_id = int(self.select_target.values[0])
        self.target = self.game.players.get(target_id)
        if not self.target:
            await interaction.response.send_message("❌ 상대방을 찾을 수 없습니다.", ephemeral=True)
            return
            
        if not self.target.heroes:
            await interaction.response.send_message("❌ 해당 플레이어는 보유한 영웅이 없어 트레이드가 불가능합니다.", ephemeral=True)
            return
            
        # 2단계: 내 영웅 선택 드롭다운으로 갱신
        self.clear_items()
        
        options = []
        for idx, h in enumerate(self.proposer.heroes):
            options.append(discord.SelectOption(
                label=f"[{h.role}] {h.name} (스탯: {h.stat})",
                value=str(idx)
            ))
            
        self.select_my_hero = discord.ui.Select(
            placeholder="내 보낼 영웅을 선택하세요.",
            min_values=1,
            max_values=1,
            options=options
        )
        self.select_my_hero.callback = self.select_my_hero_callback
        self.add_item(self.select_my_hero)
        
        await interaction.response.edit_message(
            content=f"🔽 **[2단계]** 보낼 내 영웅을 선택하세요. (대상: {self.target.member.mention})",
            view=self
        )
        
    async def select_my_hero_callback(self, interaction: discord.Interaction):
        idx = int(self.select_my_hero.values[0])
        if idx >= len(self.proposer.heroes):
            await interaction.response.send_message("❌ 영웅 정보가 올바르지 않습니다.", ephemeral=True)
            return
            
        self.my_hero = self.proposer.heroes[idx]
        
        # 3단계: 상대방 영웅 선택 드롭다운으로 갱신
        self.clear_items()
        
        options = []
        for idx, h in enumerate(self.target.heroes):
            options.append(discord.SelectOption(
                label=f"[{h.role}] {h.name} (스탯: {h.stat})",
                value=str(idx)
            ))
            
        self.select_target_hero = discord.ui.Select(
            placeholder=f"{self.target.member.display_name}님의 영웅을 선택하세요.",
            min_values=1,
            max_values=1,
            options=options
        )
        self.select_target_hero.callback = self.select_target_hero_callback
        self.add_item(self.select_target_hero)
        
        await interaction.response.edit_message(
            content=f"🔽 **[3단계]** 트레이드해 올 {self.target.member.mention}님의 영웅을 선택하세요. (내 영웅: [{self.my_hero.name}])",
            view=self
        )
        
    async def select_target_hero_callback(self, interaction: discord.Interaction):
        idx = int(self.select_target_hero.values[0])
        if idx >= len(self.target.heroes):
            await interaction.response.send_message("❌ 영웅 정보가 올바르지 않습니다.", ephemeral=True)
            return
            
        self.target_hero = self.target.heroes[idx]
        
        # 4단계: 추가금 입력 모달 띄우기
        modal = HeroMarketTradePriceModal(self.game, self.proposer, self.target, self.my_hero, self.target_hero)
        await interaction.response.send_modal(modal)

class HeroMarketTradePriceModal(discord.ui.Modal):
    def __init__(self, game, proposer, target, my_hero, target_hero):
        super().__init__(title="트레이드 정산금 입력")
        self.game = game
        self.proposer = proposer
        self.target = target
        self.my_hero = my_hero
        self.target_hero = target_hero
        
        self.extra_cash = discord.ui.TextInput(
            label="추가 금액 (만 원 단위, 주면 양수, 받으면 음수)",
            placeholder="예: 주는 금액 500, 받는 금액 -300",
            min_length=1,
            max_length=10
        )
        self.add_item(self.extra_cash)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if self.my_hero not in self.proposer.heroes:
            await interaction.followup.send("❌ 내가 보유하고 있지 않은 영웅입니다.", ephemeral=True)
            return
        if self.target_hero not in self.target.heroes:
            await interaction.followup.send("❌ 상대방이 해당 영웅을 보유하고 있지 않습니다.", ephemeral=True)
            return
            
        cash_val = self.extra_cash.value
        try:
            for char in ["만", "원", ",", " "]:
                cash_val = cash_val.replace(char, "")
            cash = int(cash_val)
        except ValueError:
            await interaction.followup.send("❌ 올바른 숫자를 입력해주세요.", ephemeral=True)
            return
            
        if cash % 100 != 0:
            await interaction.followup.send("❌ 거래 및 제안 금액은 반드시 100만 원 단위여야 합니다. (1만 원, 10만 원 단위 꼼수 불가)", ephemeral=True)
            return
            
        if cash > 0:
            if self.proposer.capital < cash:
                await interaction.followup.send(f"❌ 본인의 잔액이 부족합니다. (내 잔액: {self.proposer.capital}만 원)", ephemeral=True)
                return
        elif cash < 0:
            needed = abs(cash)
            if self.target.capital < needed:
                await interaction.followup.send(f"❌ 상대방의 잔액이 부족합니다. (상대 잔액: {self.target.capital}만 원)", ephemeral=True)
                return
                
        self.game.prop_counter += 1
        prop_id = f"trade_{self.game.prop_counter}"
        
        proposal = {
            "id": prop_id,
            "type": "trade",
            "proposer_id": self.proposer.member.id,
            "target_id": self.target.member.id,
            "hero_name": self.my_hero.name,
            "target_hero_name": self.target_hero.name,
            "price": cash,
            "status": "pending"
        }
        self.game.proposals[prop_id] = proposal
        
        view = HeroMarketProposalView(self.game, prop_id)
        msg = await interaction.channel.send(
            content=f"📬 {self.target.member.mention}님, {interaction.user.mention}님이 **[비밀 트레이드 제안]**을 보냈습니다. 아래 버튼을 눌러 확인하세요.",
            view=view
        )
        proposal["msg_id"] = msg.id
        await interaction.followup.send("✅ 트레이드 제안이 성공적으로 발송되었습니다.", ephemeral=True)

class HeroMarketProposalView(discord.ui.View):
    def __init__(self, game, prop_id):
        super().__init__(timeout=None)
        self.game = game
        self.prop_id = prop_id

    @discord.ui.button(label="📬 비밀 제안 확인", style=discord.ButtonStyle.primary)
    async def check_proposal(self, interaction: discord.Interaction, button: discord.ui.Button):
        proposal = self.game.proposals.get(self.prop_id)
        if not proposal or proposal["status"] != "pending":
            await interaction.response.send_message("❌ 이 제안은 이미 만료되었거나 취소되었습니다.", ephemeral=True)
            return
        if interaction.user.id != proposal["target_id"]:
            await interaction.response.send_message("❌ 이 제안은 본인에게 온 제안이 아닙니다.", ephemeral=True)
            return
            
        proposer = self.game.players[proposal["proposer_id"]]
        target = self.game.players[proposal["target_id"]]
        
        embed = discord.Embed(title="📬 도착한 비밀 제안", color=0x9B59B6)
        
        if proposal["type"] == "sell":
            hero = find_owned_hero(proposer, proposal["hero_name"])
            if not hero:
                await interaction.response.send_message("❌ 판매자가 제안한 영웅을 더 이상 보유하고 있지 않습니다.", ephemeral=True)
                return
            stat_str = f"{hero.stat}"
            embed.description = f"{proposer.member.mention}님이 귀하에게 **[[{hero.role}] {hero.name} <스탯: {stat_str}>]**을 **{proposal['price']}만 원**에 판매하고자 합니다."
            
        elif proposal["type"] == "buy":
            hero = find_owned_hero(target, proposal["hero_name"])
            if not hero:
                await interaction.response.send_message("❌ 귀하가 제안받은 영웅을 보유하고 있지 않습니다.", ephemeral=True)
                return
            stat_str = f"{hero.stat}"
            embed.description = f"{proposer.member.mention}님이 귀하에게서 **[[{hero.role}] {hero.name} <스탯: {stat_str}>]**을 **{proposal['price']}만 원**에 구매하고자 합니다."
            
        elif proposal["type"] == "trade":
            my_hero = find_owned_hero(proposer, proposal["hero_name"])
            target_hero = find_owned_hero(target, proposal["target_hero_name"])
            if not my_hero or not target_hero:
                await interaction.response.send_message("❌ 트레이드에 필요한 영웅이 양측에 존재하지 않습니다.", ephemeral=True)
                return
                
            my_stat = f"{my_hero.stat}"
            target_stat = f"{target_hero.stat}"
            cash = proposal["price"]
            if cash > 0:
                cash_desc = f"{proposer.member.display_name}님이 추가로 **{cash}만 원**을 지급합니다."
            elif cash < 0:
                cash_desc = f"귀하({target.member.display_name}님)가 추가로 **{abs(cash)}만 원**을 지급해야 합니다."
            else:
                cash_desc = "추가 정산 금액 없이 맞트레이드합니다."
                
            embed.description = (
                f"🔄 **트레이드 제안 정보**\n\n"
                f"• **{proposer.member.display_name}**의 영웅: [[{my_hero.role}] {my_hero.name} <스탯: {my_stat}>]\n"
                f"• **{target.member.display_name}**의 영웅: [[{target_hero.role}] {target_hero.name} <스탯: {target_stat}>]\n"
                f"• **자금 정산**: {cash_desc}"
            )
            
        view = HeroMarketProposalActionView(self.game, self.prop_id, interaction.message)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class HeroMarketProposalActionView(discord.ui.View):
    def __init__(self, game, prop_id, parent_message):
        super().__init__(timeout=None)
        self.game = game
        self.prop_id = prop_id
        self.parent_message = parent_message

    @discord.ui.button(label="✅ 수락", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        proposal = self.game.proposals.get(self.prop_id)
        if not proposal or proposal["status"] != "pending":
            await interaction.followup.send("❌ 이 제안은 이미 완료되었거나 만료되었습니다.", ephemeral=True)
            return
            
        proposer_id = proposal["proposer_id"]
        target_id = proposal["target_id"]
        proposer = self.game.players.get(proposer_id)
        target = self.game.players.get(target_id)
        
        if not proposer or not target:
            await interaction.followup.send("❌ 플레이어 정보 오류입니다.", ephemeral=True)
            return
            
        if interaction.user.id != target_id:
            await interaction.followup.send("❌ 이 제안은 본인에게 온 제안이 아닙니다.", ephemeral=True)
            return
            
        if proposal["type"] == "sell":
            price = proposal["price"]
            hero_name = proposal["hero_name"]
            
            hero = find_owned_hero(proposer, hero_name)
            if not hero:
                await interaction.followup.send("❌ 판매자가 해당 영웅을 더 이상 보유하고 있지 않습니다.", ephemeral=True)
                return
            if len(target.heroes) >= 4:
                await interaction.followup.send("❌ 본인의 영웅 보유 한도(최대 4명)가 꽉 차서 구매할 수 없습니다.", ephemeral=True)
                return
            if target.capital < price:
                await interaction.followup.send("❌ 본인의 잔액이 부족하여 수락할 수 없습니다.", ephemeral=True)
                return
                
            proposer.heroes.remove(hero)
            hero.acquired_price = price
            target.heroes.append(hero)
            
            # 시장 매물 리스트에서 제거
            for item in list(self.game.market_items):
                if item.get("seller_id") == proposer_id and item.get("hero").name == hero.name:
                    self.game.market_items.remove(item)
                    break
            
            target.capital -= price
            proposer.capital += price
            proposal["status"] = "accepted"
            
            stat_reveal = f"{hero.stat}"
            await interaction.channel.send(
                f"🤝 **거래 성사**\n{proposer.member.mention}님이 {target.member.mention}님에게 **[[{hero.role}] {hero_name} <스탯: {stat_reveal}>]**을 **{price}만 원**에 판매 완료하였습니다!"
            )
            self.game.transaction_logs.append(
                f"🤝 [판매] {proposer.member.display_name} ➔ {target.member.display_name} ([{hero.role}] {hero_name} <스탯: {stat_reveal}>, {price}만 원)"
            )
            
        elif proposal["type"] == "buy":
            price = proposal["price"]
            hero_name = proposal["hero_name"]
            
            hero = find_owned_hero(target, hero_name)
            if not hero:
                await interaction.followup.send("❌ 본인이 제안받은 영웅을 더 이상 보유하고 있지 않습니다.", ephemeral=True)
                return
            if len(proposer.heroes) >= 4:
                await interaction.followup.send("❌ 구매자의 영웅 보유 한도(최대 4명)가 꽉 차서 수락할 수 없습니다.", ephemeral=True)
                return
            if proposer.capital < price:
                await interaction.followup.send("❌ 제안자의 잔액이 부족하여 거래가 취소됩니다.", ephemeral=True)
                proposal["status"] = "cancelled"
                await self.disable_parent_message("❌ 제안자 잔액 부족으로 무산")
                return
                
            target.heroes.remove(hero)
            hero.acquired_price = price
            proposer.heroes.append(hero)
            
            # 시장 매물 리스트에서 제거
            for item in list(self.game.market_items):
                if item.get("seller_id") == target_id and item.get("hero").name == hero.name:
                    self.game.market_items.remove(item)
                    break
            
            proposer.capital -= price
            target.capital += price
            proposal["status"] = "accepted"
            
            stat_reveal = f"{hero.stat}"
            await interaction.channel.send(
                f"🤝 **거래 성사**\n{proposer.member.mention}님이 {target.member.mention}님으로부터 **[[{hero.role}] {hero_name} <스탯: {stat_reveal}>]**을 **{price}만 원**에 구매 완료하였습니다!"
            )
            self.game.transaction_logs.append(
                f"🤝 [구매] {proposer.member.display_name} ➔ {target.member.display_name} ([{hero.role}] {hero_name} <스탯: {stat_reveal}>, {price}만 원)"
            )
            
        elif proposal["type"] == "trade":
            cash = proposal["price"]
            my_hero_name = proposal["hero_name"]
            target_hero_name = proposal["target_hero_name"]
            
            my_hero = find_owned_hero(proposer, my_hero_name)
            target_hero = find_owned_hero(target, target_hero_name)
            
            if not my_hero or not target_hero:
                await interaction.followup.send("❌ 트레이드에 필요한 영웅이 양측에 존재하지 않습니다.", ephemeral=True)
                return
                
            if cash > 0:
                if proposer.capital < cash:
                    await interaction.followup.send("❌ 제안자 잔액 부족으로 트레이드를 수락할 수 없습니다.", ephemeral=True)
                    proposal["status"] = "cancelled"
                    await self.disable_parent_message("❌ 제안자 잔액 부족으로 무산")
                    return
            elif cash < 0:
                needed = abs(cash)
                if target.capital < needed:
                    await interaction.followup.send("❌ 본인의 잔액이 부족하여 트레이드를 수락할 수 없습니다.", ephemeral=True)
                    return
                    
            proposer.heroes.remove(my_hero)
            target.heroes.remove(target_hero)
            proposer.heroes.append(target_hero)
            target.heroes.append(my_hero)
            
            # 시장 매물 리스트에서 제거
            for item in list(self.game.market_items):
                if (item.get("seller_id") == proposer_id and item.get("hero").name == my_hero.name) or \
                   (item.get("seller_id") == target_id and item.get("hero").name == target_hero.name):
                    try:
                        self.game.market_items.remove(item)
                    except ValueError:
                        pass
            
            if cash > 0:
                proposer.capital -= cash
                target.capital += cash
            elif cash < 0:
                needed = abs(cash)
                target.capital -= needed
                proposer.capital += needed
                
            proposal["status"] = "accepted"
            
            my_stat = f"{my_hero.stat}"
            target_stat = f"{target_hero.stat}"
            cash_reveal = f" (정산금: {abs(cash)}만 원 {'지급' if cash > 0 else '수령'})" if cash != 0 else ""
            
            await interaction.channel.send(
                f"🤝 **트레이드 성사**\n{proposer.member.mention}의 **[[{my_hero.role}] {my_hero_name} <스탯: {my_stat}>]** ⇄ {target.member.mention}의 **[[{target_hero.role}] {target_hero_name} <스탯: {target_stat}>]**{cash_reveal} 거래가 체결되었습니다!"
            )
            self.game.transaction_logs.append(
                f"🤝 [트레이드] {proposer.member.display_name}의 [{my_hero.role}] {my_hero_name}({my_stat}) ⇄ {target.member.display_name}의 [{target_hero.role}] {target_hero_name}({target_stat}){cash_reveal}"
            )
            
        await interaction.followup.send("✅ 제안을 수락하였습니다.", ephemeral=True)
        await self.disable_parent_message("✅ 거래 완료")
        await update_marketplace_main_message(interaction.channel, self.game)

    @discord.ui.button(label="❌ 거절", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        proposal = self.game.proposals.get(self.prop_id)
        if not proposal or proposal["status"] != "pending":
            await interaction.followup.send("❌ 이 제안은 이미 완료되었거나 만료되었습니다.", ephemeral=True)
            return
            
        target_id = proposal["target_id"]
        if interaction.user.id != target_id:
            await interaction.followup.send("❌ 이 제안은 본인에게 온 제안이 아닙니다.", ephemeral=True)
            return
            
        proposal["status"] = "declined"
        proposer = self.game.players.get(proposal["proposer_id"])
        
        await interaction.followup.send("❌ 제안을 거절하였습니다.", ephemeral=True)
        if proposer:
            try:
                await proposer.member.send(f"📬 {interaction.user.display_name}님이 보낸 제안({proposal['hero_name']})을 거절하셨습니다.")
            except:
                pass
        await self.disable_parent_message("❌ 제안 거절됨")

    async def disable_parent_message(self, status_text):
        try:
            view = discord.ui.View()
            btn = discord.ui.Button(label="제안 완료", disabled=True, style=discord.ButtonStyle.secondary)
            view.add_item(btn)
            await self.parent_message.edit(content=f"📬 이 제안은 종료되었습니다. ({status_text})", embed=None, view=view)
        except Exception as e:
            print(f"Error disabling parent msg: {e}")

# --- [다음 라운드 및 종료 처리] ---
async def next_round(channel, game):
    game.round += 1
    if game.round > game.total_rounds:
        await end_hero_market(channel, game)
    else:
        await start_auction_round(channel, game)

class HeroCaptainSelect(discord.ui.Select):
    def __init__(self, player, game, parent_view):
        self.player = player
        self.game = game
        self.parent_view = parent_view
        options = []
        for idx, h in enumerate(player.heroes):
            options.append(discord.SelectOption(label=f"[{h.role}] {h.name} (스탯: {h.stat})", value=str(idx)))
        super().__init__(placeholder="주장 영웅을 선택하세요.", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        if idx < len(self.player.heroes):
            self.player.tournament_captain = self.player.heroes[idx]
            
            remaining_heroes = [h for h in self.player.heroes if h != self.player.tournament_captain]
            
            if len(remaining_heroes) == 0:
                await interaction.response.edit_message(
                    content=f"✅ 주장: **[{self.player.tournament_captain.role}] {self.player.tournament_captain.name}**을(를) 설정 완료했습니다! (호위로 출전할 남은 영웅이 없습니다.)", 
                    view=None
                )
                await self.parent_view.check_selections(interaction)
            else:
                current_view = self.view
                current_view.clear_items()
                current_view.add_item(HeroGuardSelect(self.player, self.game, self.parent_view, remaining_heroes))
                
                await interaction.response.edit_message(
                    content="🛡️ **[2단계] 호위로 출전할 영웅을 고르세요.** (주장으로 고른 영웅은 제외되었습니다.)",
                    view=current_view
                )
        else:
            await interaction.response.send_message("❌ 영웅 정보가 올바르지 않습니다.", ephemeral=True)

class HeroGuardSelect(discord.ui.Select):
    def __init__(self, player, game, parent_view, remaining_heroes):
        self.player = player
        self.game = game
        self.parent_view = parent_view
        self.remaining_heroes = remaining_heroes
        
        options = []
        for idx, h in enumerate(remaining_heroes):
            options.append(discord.SelectOption(label=f"[{h.role}] {h.name} (스탯: {h.stat})", value=str(idx)))
            
        min_val = min(2, len(remaining_heroes))
        super().__init__(
            placeholder="호위 영웅을 선택하세요.",
            min_values=min_val,
            max_values=min_val,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_guards = []
        for val in self.values:
            idx = int(val)
            if idx < len(self.remaining_heroes):
                selected_guards.append(self.remaining_heroes[idx])
                
        self.player.tournament_guards = selected_guards
        guards_str = ", ".join(f"[{h.role}] {h.name}" for h in selected_guards)
        
        await interaction.response.edit_message(
            content=f"✅ 주장: **[{self.player.tournament_captain.role}] {self.player.tournament_captain.name}**\n"
                    f"✅ 호위: **{guards_str}**\n"
                    f"출전 세팅이 모두 완료되었습니다!",
            view=None
        )
        await self.parent_view.check_selections(interaction)

class HeroMarketTournamentView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game
        self.is_processing = False

    @discord.ui.button(label="⚔️ 출전 세팅", style=discord.ButtonStyle.primary)
    async def setup_entry(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id not in self.game.players:
            await interaction.response.send_message("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
            
        player = self.game.players[user_id]
        if player.tournament_captain is not None:
            await interaction.response.send_message("❌ 이미 출전 세팅을 완료하셨습니다.", ephemeral=True)
            return
            
        if not player.heroes:
            player.tournament_captain = "None"
            player.tournament_guards = []
            await interaction.response.send_message("❌ 보유한 영웅이 없습니다. (모든 스탯 0 처리)", ephemeral=True)
            await self.check_selections(interaction)
            return
            
        view = discord.ui.View()
        view.add_item(HeroCaptainSelect(player, self.game, self))
        await interaction.response.send_message("👉 아래 드롭다운 메뉴에서 주장으로 출전할 영웅을 선택하세요.", view=view, ephemeral=True)

    async def check_selections(self, interaction: discord.Interaction):
        if self.is_processing:
            return
            
        def is_player_ready(p):
            if p.tournament_captain is None:
                return False
            if p.tournament_captain == "None":
                return True
            needed_guards = min(2, len(p.heroes) - 1)
            return len(p.tournament_guards) == needed_guards
            
        if all(is_player_ready(p) for p in self.game.players.values()):
            self.is_processing = True
            self.stop()
            try:
                await interaction.message.edit(content="⚔️ 모든 참가자가 출전 세팅을 완료했습니다! 천하무술대회를 시작합니다.", view=None)
            except:
                pass
            asyncio.create_task(run_tournament_battle(interaction.channel, self.game))

async def run_tournament_battle(channel, game):
    await asyncio.sleep(3)
    
    player_scores = {}
    for pid, p in game.players.items():
        captain_base = p.tournament_captain.stat if (p.tournament_captain and p.tournament_captain != "None") else 0
        guards_base = sum(g.stat for g in p.tournament_guards if g)
        total_stat = captain_base + guards_base
        
        captain_hero = p.tournament_captain
        if captain_hero == "None" or captain_hero is None:
            captain_hero = None
            captain_stat = 0
            raw_captain_stat = 0
            captain_penalty = False
        else:
            raw_captain_stat = captain_hero.stat
            if captain_hero.role == '호위':
                captain_stat = int(raw_captain_stat * 0.5)
                captain_penalty = True
            else:
                captain_stat = raw_captain_stat
                captain_penalty = False
            
        front_mid_heroes = p.tournament_guards
        
        front_mid_stat = 0
        fm_info_list = []
        for h in front_mid_heroes:
            raw_stat = h.stat
            if h.role == '주장':
                final_stat = int(raw_stat * 0.5)
                is_penalized = True
            else:
                final_stat = raw_stat
                is_penalized = False
            front_mid_stat += final_stat
            fm_info_list.append((h, final_stat, is_penalized))
        
        player_scores[pid] = {
            'player': p,
            'total': total_stat,
            'front_mid': front_mid_stat,
            'captain': captain_stat,
            'raw_captain': raw_captain_stat,
            'captain_penalty': captain_penalty,
            'points': 0,
            'front_mid_heroes_info': fm_info_list
        }
        
    # --- 보너스 [총 능력치 (1점)] ---
    max_total = max(s['total'] for s in player_scores.values())
    total_winners = []
    for pid, s in player_scores.items():
        if s['total'] == max_total:
            s['points'] += 1
            total_winners.append(s['player'].member.display_name)
            
    embed_bonus = discord.Embed(
        title="🔥 [천하무술대회] 보너스 라운드: 총 능력치 비교",
        description="벤치에 있는 영웅을 제외하고, 실제 출전한 주장과 호위의 순수 스탯 합계 (포지션 패널티 미적용)가 가장 높은 유저가 승점을 가져갑니다!",
        color=0x3498DB
    )
    for pid, s in player_scores.items():
        embed_bonus.add_field(
            name=s['player'].member.display_name,
            value=f"• 순수 총 능력치: **{s['total']}**",
            inline=False
        )
    embed_bonus.add_field(
        name="🏆 결과",
        value=f"최고 총합: **{max_total}**\n획득자 (승점 +1): **{', '.join(total_winners)}**",
        inline=False
    )
    await channel.send(embed=embed_bonus)
    await asyncio.sleep(3)
    
    # --- 1라운드 [선봉+중견 전 (2점)] ---
    max_front_mid = max(s['front_mid'] for s in player_scores.values())
    front_mid_winners = []
    for pid, s in player_scores.items():
        if s['front_mid'] == max_front_mid:
            s['points'] += 2
            front_mid_winners.append(s['player'].member.display_name)
            
    embed_r1 = discord.Embed(
        title="⚔️ [천하무술대회] 1라운드: 호위 전",
        description="주장을 제외한 영웅들 중 스탯이 가장 높은 2명의 합산(포지션 패널티 적용)이 가장 높은 유저가 승점을 가져갑니다!\n(주장 영웅이 호위 자리로 출전하면 스탯이 50% 삭감됩니다)",
        color=0xE67E22
    )
    for pid, s in player_scores.items():
        captain_name = s['player'].tournament_captain.name if (s['player'].tournament_captain and s['player'].tournament_captain != "None") else "없음"
        fm_info = s.get('front_mid_heroes_info', [])
        fm_details = []
        for h, final_stat, is_penalized in fm_info:
            penalty_text = " (⚠️50% 삭감)" if is_penalized else ""
            fm_details.append(f"[{h.role}] {h.name}({final_stat}{penalty_text})")
        fm_str = ", ".join(fm_details) if fm_details else "없음"
        embed_r1.add_field(
            name=s['player'].member.display_name,
            value=f"• 호위 최종 합산: **{s['front_mid']}**\n  └ 출전: {fm_str} (주장 {captain_name} 제외)",
            inline=False
        )
    embed_r1.add_field(
        name="🏆 결과",
        value=f"최고 호위: **{max_front_mid}**\n획득자 (승점 +2): **{', '.join(front_mid_winners)}**",
        inline=False
    )
    await channel.send(embed=embed_r1)
    await asyncio.sleep(3)
    
    # --- 2라운드 [대장 전 (1점)] ---
    max_captain = max(s['captain'] for s in player_scores.values())
    captain_winners = []
    for pid, s in player_scores.items():
        if s['captain'] == max_captain:
            s['points'] += 1
            captain_winners.append(s['player'].member.display_name)
            
    embed_r2 = discord.Embed(
        title="👑 [천하무술대회] 2라운드: 주장 전",
        description="각자 출전시킨 주장 영웅의 능력치(포지션 패널티 적용)를 직접 비교합니다!\n(호위 영웅이 주장 자리로 출전하면 스탯이 50% 삭감됩니다)",
        color=0x9B59B6
    )
    for pid, s in player_scores.items():
        captain_hero = s['player'].tournament_captain
        if captain_hero and captain_hero != "None":
            penalty_text = " (⚠️50% 삭감)" if s['captain_penalty'] else ""
            captain_desc = f"[{captain_hero.role}] {captain_hero.name} (최종 스탯: **{s['captain']}**{penalty_text})"
        else:
            captain_desc = "없음"
        embed_r2.add_field(
            name=s['player'].member.display_name,
            value=f"• 주장: {captain_desc}",
            inline=False
        )
    embed_r2.add_field(
        name="🏆 결과",
        value=f"최고 주장: **{max_captain}**\n획득자 (승점 +1): **{', '.join(captain_winners)}**",
        inline=False
    )
    await channel.send(embed=embed_r2)
    await asyncio.sleep(3)
    
    # --- 최종 결과 발표 ---
    max_points = max(s['points'] for s in player_scores.values())
    winners = [s['player'] for s in player_scores.values() if s['points'] == max_points]
    
    embed_final = discord.Embed(
        title="🏆 [천하무술대회] 최종 순위 및 결과 발표 🏆",
        description="모든 라운드가 성황리에 종료되었습니다! 오늘의 천하제일 우승자는?",
        color=0xF1C40F
    )
    
    winner_mentions = ", ".join(w.member.mention for w in winners)
    embed_final.add_field(
        name="🥇 천하제일 우승자",
        value=f"🎉 {winner_mentions} (최종 승점: **{max_points}점**)",
        inline=False
    )
    
    leaderboard = []
    sorted_scores = sorted(player_scores.values(), key=lambda x: (x['points'], x['total']), reverse=True)
    for i, s in enumerate(sorted_scores):
        captain_hero = s['player'].tournament_captain
        if captain_hero and captain_hero != "None":
            captain_name = captain_hero.name
            captain_role = captain_hero.role
            penalty_text = " (⚠️50% 삭감)" if s['captain_penalty'] else ""
            captain_str = f"[{captain_role}] {captain_name}(최종 {s['captain']}{penalty_text})"
        else:
            captain_str = "없음"
            
        hero_details = [f"[{h.role}] {h.name}({h.stat})" for h in s['player'].heroes]
        heroes_str = ", ".join(hero_details) if hero_details else "없음"
        leaderboard.append(
            f"**{i+1}등** {s['player'].member.display_name}: **{s['points']}점**\n"
            f"  └ 주장: {captain_str} / 호위(최종): {s['front_mid']} / 순수 총 스탯: {s['total']}\n"
            f"  └ 보유 영웅: {heroes_str}"
        )
        
    embed_final.add_field(name="📊 종합 순위표", value="\n".join(leaderboard), inline=False)
    await channel.send(embed=embed_final)
    
    if channel.guild.voice_client:
        try:
            channel.guild.voice_client.stop()
        except:
            pass
            
    if game.cid in hero_market_games:
        del hero_market_games[game.cid]

async def end_hero_market(channel, game):
    vc = channel.guild.voice_client
    if vc is None or not vc.is_connected():
        if game.host and getattr(game.host, "voice", None) and game.host.voice.channel:
            try:
                vc = await game.host.voice.channel.connect()
            except Exception as e:
                print(f"음성 채널 연결 실패: {e}")
    else:
        try:
            vc.stop()
        except:
            pass
            
    try:
        await play_hero_market_bgm(channel, "judgment.mp3")
    except Exception as e:
        print(f"BGM 재생 실패: {e}")
        
    embed = discord.Embed(
        title="⚔️ 천하무술대회 개막!",
        description="최종 이적시장이 종료되었습니다. 이제 보유한 영웅들로 천하무술대회를 시작합니다!\n"
                    "아래 **[출전 세팅]** 버튼을 눌러 주장으로 나설 영웅을 1명 선택하세요.\n"
                    "(나머지 영웅들은 자동으로 호위로 편성됩니다. 보유 자금은 소멸합니다.)",
        color=0xE74C3C
    )
    
    view = HeroMarketTournamentView(game)
    await channel.send(embed=embed, view=view)

# --- [모집 및 시작 뷰] ---
class HeroMarketJoinView(discord.ui.View):
    def __init__(self, host):
        super().__init__(timeout=120.0)
        self.host = host
        self.players = [host]

    @discord.ui.button(label="⚔️ 영웅문 참가", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user in self.players:
            await interaction.followup.send("이미 참가 중입니다!", ephemeral=True)
            return
            
        self.players.append(interaction.user)
        embed = interaction.message.embeds[0]
        embed.description = (
            f"초기 자금 3,000만 원으로 입찰하고 이적시장에서 영웅을 거래하여 최강의 진형을 꾸리세요!\n\n"
            f"**현재 참가자:** {' '.join([p.mention for p in self.players])}\n"
            f"(최소 2명 필요)"
        )
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="🚀 게임 시작", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user != self.host:
            await interaction.followup.send("방장만 게임을 시작할 수 있습니다!", ephemeral=True)
            return
        if len(self.players) < 2:
            await interaction.followup.send("최소 2명 이상 참여해야 합니다!", ephemeral=True)
            return
            
        self.stop()
        
        try:
            vc = interaction.guild.voice_client
            if vc:
                await play_hero_market_bgm(interaction, "Heromarket.mp3")
        except Exception as e:
            print(f"BGM 전환 실패: {e}")
            
        hero_pool = load_hero_names()
        game = HeroMarketGame(interaction.channel_id, self.host, self.players, hero_pool)
        hero_market_games[interaction.channel_id] = game
        
        await interaction.channel.send("🎮 **영웅문 게임이 시작되었습니다!**")
        await start_auction_round(interaction.channel, game)

# --- [디스코드 명령어 바인딩] ---

@bot.command(name="영웅문")
async def cmd_hero_market(ctx):
    cid = ctx.channel.id
    if cid in hero_market_games:
        await ctx.send("❌ 이미 진행 중인 영웅문 게임이 있습니다.")
        return
        
    if ctx.author.voice:
        if ctx.voice_client is None:
            try: await ctx.author.voice.channel.connect()
            except: pass
        elif ctx.voice_client.channel != ctx.author.voice.channel:
            try: await ctx.voice_client.move_to(ctx.author.voice.channel)
            except: pass

    try:
        if ctx.voice_client:
            await play_hero_market_bgm(ctx, "intro.mp3")
    except Exception as e:
        print(f"BGM 재생 실패: {e}")

    view = HeroMarketJoinView(ctx.author)
    embed = discord.Embed(
        title="🎮 [영웅문] 게임 모집 시작",
        description=f"초기 자금 3,000만 원으로 입찰하고 이적시장에서 영웅을 거래하여 최강의 진형을 꾸리세요!\n\n"
                    f"**현재 참가자:** {ctx.author.mention}\n"
                    f"(최소 2명 필요)",
        color=0xE74C3C
    )
    await ctx.send(embed=embed, view=view)

@bot.command(name="잔액")
async def cmd_balance(ctx):
    cid = ctx.channel.id
    if cid not in hero_market_games:
        await ctx.send("❌ 현재 채널에서 진행 중인 영웅문 게임이 없습니다.")
        return
        
    game = hero_market_games[cid]
    if ctx.author.id not in game.players:
        await ctx.send("❌ 게임 참가자만 잔액 조회가 가능합니다.")
        return
        
    view = HeroMarketBalanceView(game)
    await ctx.send(f"👉 아래 버튼을 누르면 **{ctx.author.display_name}**님의 잔고와 영웅 목록을 비공개로 확인합니다.", view=view)

@bot.command(name="스쿼드")
async def cmd_squad(ctx):
    cid = ctx.channel.id
    if cid not in hero_market_games:
        await ctx.send("❌ 현재 채널에서 진행 중인 영웅문 게임이 없습니다.")
        return
        
    game = hero_market_games[cid]
    if ctx.author.id not in game.players:
        await ctx.send("❌ 게임 참가자만 스쿼드 조회가 가능합니다.")
        return
        
    view = HeroMarketSquadView(game)
    await ctx.send(f"👉 아래 버튼을 누르면 **{ctx.author.display_name}**님의 스쿼드(보유 영웅)를 비공개로 확인합니다.", view=view)

class HeroMarketSquadView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="⚔️ 내 스쿼드 확인", style=discord.ButtonStyle.primary)
    async def check_my_squad(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id not in self.game.players:
            await interaction.response.send_message("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
            
        player = self.game.players[user_id]
        embed = discord.Embed(title=f"⚔️ {interaction.user.display_name}님의 스쿼드 현황", color=0x2ECC71)
        
        hero_details = [f"• **[{h.role}] {h.name}** (스탯: **{h.stat}**, 구매가: **{h.acquired_price}만 원**)" for h in player.heroes]
        heroes_str = "\n".join(hero_details) if hero_details else "보유하고 있는 영웅이 없습니다."
        embed.add_field(name=f"보유 영웅 목록 ({len(player.heroes)}/4명)", value=heroes_str, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class HeroMarketBalanceView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=None)
        self.game = game

    @discord.ui.button(label="💳 내 잔액 확인", style=discord.ButtonStyle.secondary)
    async def check_my_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id not in self.game.players:
            await interaction.response.send_message("❌ 이 게임의 참가자가 아닙니다.", ephemeral=True)
            return
            
        player = self.game.players[user_id]
        embed = discord.Embed(title=f"💳 {interaction.user.display_name}님의 재정 상태", color=0x3498DB)
        if getattr(player, "locked_funds", 0) > 0:
            cap_str = f"💰 **{player.capital}만 원 (입찰 중 묶인 금액: {player.locked_funds}만 원)**"
        else:
            cap_str = f"💰 **{player.capital}만 원**"
        embed.add_field(name="보유 자본", value=cap_str, inline=False)
        
        hero_details = [f"• **[{h.role}] {h.name}** (스탯: **{h.stat}**, 구매가: **{h.acquired_price}만 원**)" for h in player.heroes]
        heroes_str = "\n".join(hero_details) if hero_details else "보유하고 있는 영웅이 없습니다."
        embed.add_field(name=f"보유 영웅 목록 ({len(player.heroes)}/4명)", value=heroes_str, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="내역")
async def cmd_history(ctx):
    cid = ctx.channel.id
    if cid not in hero_market_games:
        await ctx.send("❌ 현재 채널에서 진행 중인 영웅문 게임이 없습니다.")
        return
        
    game = hero_market_games[cid]
    if not game.transaction_logs:
        await ctx.send("📜 기록된 거래 내역이 아직 없습니다.")
        return
        
    embed = discord.Embed(
        title="📜 [영웅문] 전체 거래 내역",
        description="\n".join(game.transaction_logs),
        color=0xF39C12
    )
    await ctx.send(embed=embed)

@bot.command(name="영웅문종료")
async def cmd_stop_hero_market(ctx):
    cid = ctx.channel.id
    if cid in hero_market_games:
        del hero_market_games[cid]
        if ctx.voice_client:
            try: ctx.voice_client.stop()
            except: pass
        await ctx.send("🛑 영웅문 게임을 강제 종료했습니다.")
    else:
        await ctx.send("❌ 진행 중인 영웅문 게임이 없습니다.")

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

token = os.getenv("DISCORD_BOT_TOKEN")
if not token and os.path.exists("토큰.txt"):
    with open("토큰.txt", "r", encoding="utf-8") as f:
        token = f.read().strip()
elif not token and os.path.exists("token.txt"):
    with open("token.txt", "r", encoding="utf-8") as f:
        token = f.read().strip()
if not token:
    token = os.getenv("BOT_TOKEN")

if not token:
    raise ValueError("디스코드 봇 토큰을 환경 변수(DISCORD_BOT_TOKEN) 또는 토큰.txt 파일에 설정해주세요.")

bot.run(token)



