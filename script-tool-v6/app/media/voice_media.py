"""v6：角色配音（CosyVoice 语音合成）+ 音画混流。

- 走 DashScope SDK 的 SpeechSynthesizer（WebSocket），复用项目现有 DASHSCOPE_API_KEY；
- 提供分类音色库（官方 v3-flash 全量 87 个，按 性别×年龄/风格 分组），标注是否支持「情感指令(Instruct)」；
- 每句台词（字幕 cue）合成一段音频，可调 音色 / 情绪 / 语速 / 音调 / 音量 / seed；
- 用 ffmpeg 按 cue 时间轴把各段配音 adelay 定位 + amix 混合后 mux 进视频
  （复用 subtitles.py 已验证的 ffmpeg 调用方式）。

约束（据阿里云百炼官方音色列表，2026-10 核对）：
- CosyVoice v1 已下线，只能用 v2 / v3；默认 cosyvoice-v3-flash（音色最多、部分支持情感）。
- 「情绪」依赖 instruction，仅少数音色支持（见 instruct=True），且情感值固定 7 种；
  不支持情感的音色，情绪会自动降级为「用 音调/语速/音量 近似表达」。
- 语速(speech_rate)、音调(pitch_rate)、音量(volume) 是所有音色都支持的构造参数。

SDK 的 call() 为同步阻塞，路由层请用 asyncio.to_thread 调用。
"""
import subprocess
from pathlib import Path

from app.config import (DASHSCOPE_API_KEY, COSYVOICE_MODEL, COSYVOICE_WS_URL,
                        COSYVOICE_DEFAULT_VOICE, COSYVOICE_FORMAT,
                        COSYVOICE_DEFAULT_VOLUME, COSYVOICE_DEFAULT_SPEECH_RATE,
                        COSYVOICE_DEFAULT_PITCH_RATE)
from app.media.dashscope_media import _ffmpeg_exe

# ── 情感（CosyVoice Instruct 固定 7 值；指令文本必须中文且严格格式）──────
EMOTIONS = {                      # 英文情感值 -> 中文名
    "neutral": "平静", "happy": "高兴", "sad": "悲伤", "angry": "愤怒",
    "fearful": "恐惧", "surprised": "惊讶", "disgusted": "厌恶",
}
_EMOTION_ALIAS = {                # 中文/常见别名 -> 英文情感值（前端可传中文）
    "平静": "neutral", "中性": "neutral", "高兴": "happy", "喜悦": "happy",
    "开心": "happy", "悲伤": "sad", "难过": "sad", "愤怒": "angry", "生气": "angry",
    "恐惧": "fearful", "害怕": "fearful", "惊讶": "surprised", "惊奇": "surprised",
    "厌恶": "disgusted", "嫌弃": "disgusted",
}


def normalize_emotion(emotion) -> str:
    """把中英文情感统一成 CosyVoice 情感值（neutral/happy/...）；无效返回空串。"""
    e = str(emotion or "").strip()
    if not e:
        return ""
    low = e.lower()
    if low in EMOTIONS:
        return low
    return _EMOTION_ALIAS.get(e, "")


def build_instruction(emotion: str, scene: str = "", role: str = "") -> str:
    """按 CosyVoice 官方格式拼情感指令（中文、严格标点、结尾句号）。

    仅对支持 Instruct 的音色有效；调用方应先判断 voice_supports_instruct()。
    """
    emo = normalize_emotion(emotion)
    if not emo:
        return ""
    role = (role or "").strip()
    scene = (scene or "").strip()
    if role:
        return f"你现在说话的角色是{role}，你说话的情感是{emo}。"
    if scene:
        return f"你正在进行{scene}，你说话的情感是{emo}。"
    return f"你说话的情感是{emo}。"


# ── 音色库（id 为 voice 参数；instruct=是否支持情感指令）──────────────
# 每项：id, name, gender, age, trait, instruct, lang。默认模型 cosyvoice-v3-flash。
# 官方 v3-flash 全量 87 个，按 性别×年龄 / 风格 分组，便于按男女老少挑选。
VOICE_LIBRARY = [
    {"category": "男声·青年(19-35)", "voices": [
        {"id": "longanyang", "name": "龙安洋", "gender": "男", "age": "20-30", "trait": "阳光大男孩", "instruct": True, "lang": "中/英"},
        {"id": "longcheng_v3", "name": "龙橙", "gender": "男", "age": "20-25", "trait": "智慧青年", "instruct": False, "lang": "中/英"},
        {"id": "longze_v3", "name": "龙泽", "gender": "男", "age": "25-30", "trait": "温暖元气", "instruct": False, "lang": "中/英"},
        {"id": "longanlang_v3", "name": "龙安朗", "gender": "男", "age": "20-25", "trait": "清爽利落", "instruct": False, "lang": "中/英"},
        {"id": "longyichen_v3", "name": "龙逸尘", "gender": "男", "age": "20-30", "trait": "洒脱活力", "instruct": False, "lang": "中/英"},
        {"id": "longanzhi_v3", "name": "龙安智", "gender": "男", "age": "25-35", "trait": "睿智轻熟", "instruct": False, "lang": "中/英"},
        {"id": "longyingxun_v3", "name": "龙应询", "gender": "男", "age": "20-25", "trait": "年轻青涩", "instruct": False, "lang": "中/英"},
        {"id": "longshu_v3", "name": "龙书", "gender": "男", "age": "20-25", "trait": "沉稳青年", "instruct": False, "lang": "中/英"},
        {"id": "longshuo_v3", "name": "龙硕", "gender": "男", "age": "25-30", "trait": "博才干练", "instruct": False, "lang": "中/英"},
        {"id": "longnan_v3", "name": "龙楠", "gender": "男", "age": "25-30", "trait": "睿智青年", "instruct": False, "lang": "中/英"},
        {"id": "longzhe_v3", "name": "龙哲", "gender": "男", "age": "25-30", "trait": "呆板大暖男", "instruct": False, "lang": "中/英"},
        {"id": "longanyun_v3", "name": "龙安昀", "gender": "男", "age": "30-35", "trait": "居家暖男", "instruct": False, "lang": "中/英"},
    ]},
    {"category": "男声·中年(30-55)", "voices": [
        {"id": "longtian_v3", "name": "龙天", "gender": "男", "age": "30-35", "trait": "磁性理智", "instruct": False, "lang": "中/英"},
        {"id": "longfei_v3", "name": "龙飞", "gender": "男", "age": "30-35", "trait": "热血磁性", "instruct": False, "lang": "中/英"},
        {"id": "longhao_v3", "name": "龙浩", "gender": "男", "age": "30-35", "trait": "多情忧郁", "instruct": False, "lang": "中/英"},
        {"id": "longhan_v3", "name": "龙寒", "gender": "男", "age": "30-35", "trait": "温暖痴情", "instruct": False, "lang": "中/英"},
        {"id": "longsanshu_v3", "name": "龙三叔", "gender": "男", "age": "25-45", "trait": "沉稳质感", "instruct": False, "lang": "中/英"},
        {"id": "longxiu_v3", "name": "龙修", "gender": "男", "age": "25-35", "trait": "博才说书", "instruct": False, "lang": "中/英"},
    ]},
    {"category": "男声·老年(55+)", "voices": [
        {"id": "longlaobo_v3", "name": "龙老伯", "gender": "男", "age": "60+", "trait": "沧桑岁月爷", "instruct": False, "lang": "中/英"},
    ]},
    {"category": "女声·青年(19-35)", "voices": [
        {"id": "longanhuan", "name": "龙安欢", "gender": "女", "age": "20-30", "trait": "欢脱元气", "instruct": True, "lang": "中/英"},
        {"id": "longxiaochun_v3", "name": "龙小淳", "gender": "女", "age": "25-30", "trait": "知性积极", "instruct": False, "lang": "中/英"},
        {"id": "longwan_v3", "name": "龙婉", "gender": "女", "age": "20-30", "trait": "细腻柔声", "instruct": False, "lang": "中/英"},
        {"id": "longwanjun_v3", "name": "龙婉君", "gender": "女", "age": "20-30", "trait": "细腻柔声", "instruct": False, "lang": "中/英"},
        {"id": "longxing_v3", "name": "龙星", "gender": "女", "age": "20-25", "trait": "温婉邻家", "instruct": False, "lang": "中/英"},
        {"id": "longhua_v3", "name": "龙华", "gender": "女", "age": "20-25", "trait": "元气甜美", "instruct": False, "lang": "中/英"},
        {"id": "longfeifei_v3", "name": "龙菲菲", "gender": "女", "age": "20-25", "trait": "甜美娇气", "instruct": False, "lang": "中/英"},
        {"id": "longyumi_v3", "name": "YUMI", "gender": "女", "age": "20-25", "trait": "正经青年", "instruct": False, "lang": "中/英"},
        {"id": "longanli_v3", "name": "龙安莉", "gender": "女", "age": "25-35", "trait": "利落从容", "instruct": False, "lang": "中/英"},
        {"id": "longanwen_v3", "name": "龙安温", "gender": "女", "age": "25-35", "trait": "优雅知性", "instruct": False, "lang": "中/英"},
        {"id": "longanrou_v3", "name": "龙安柔", "gender": "女", "age": "20-35", "trait": "温柔闺蜜", "instruct": False, "lang": "中/英"},
        {"id": "longanqin_v3", "name": "龙安亲", "gender": "女", "age": "20-25", "trait": "亲和活泼", "instruct": False, "lang": "中/英"},
        {"id": "longantai_v3", "name": "龙安台", "gender": "女", "age": "20-25", "trait": "嗲甜台湾", "instruct": False, "lang": "中/英"},
        {"id": "longanling_v3", "name": "龙安灵", "gender": "女", "age": "20-30", "trait": "思维灵动", "instruct": False, "lang": "中/英"},
        {"id": "longyingxiao_v3", "name": "龙应笑", "gender": "女", "age": "20-25", "trait": "清甜推销", "instruct": False, "lang": "中/英"},
        {"id": "longyingtao_v3", "name": "龙应桃", "gender": "女", "age": "25-30", "trait": "温柔淡定", "instruct": False, "lang": "中/英"},
        {"id": "longyingling_v3", "name": "龙应聆", "gender": "女", "age": "25-30", "trait": "温和共情", "instruct": False, "lang": "中/英"},
        {"id": "longyingmu_v3", "name": "龙应沐", "gender": "女", "age": "25-30", "trait": "优雅知性", "instruct": False, "lang": "中/英"},
    ]},
    {"category": "女声·中年(30-55)", "voices": [
        {"id": "longyue_v3", "name": "龙悦", "gender": "女", "age": "30-35", "trait": "温暖磁性", "instruct": False, "lang": "中/英"},
        {"id": "longyuan_v3", "name": "龙媛", "gender": "女", "age": "35-40", "trait": "温暖治愈", "instruct": False, "lang": "中/英"},
        {"id": "longyan_v3", "name": "龙颜", "gender": "女", "age": "30-35", "trait": "温暖春风", "instruct": False, "lang": "中/英"},
        {"id": "longqiang_v3", "name": "龙嫱", "gender": "女", "age": "30-35", "trait": "浪漫风情", "instruct": False, "lang": "中/英"},
        {"id": "longanya_v3", "name": "龙安雅", "gender": "女", "age": "25-35", "trait": "高雅气质", "instruct": False, "lang": "中/英"},
        {"id": "longxiaoxia_v3", "name": "龙小夏", "gender": "女", "age": "25-30", "trait": "沉稳权威", "instruct": False, "lang": "中/英"},
        {"id": "longyingjing_v3", "name": "龙应静", "gender": "女", "age": "25-35", "trait": "低调冷静", "instruct": False, "lang": "中/英"},
        {"id": "longanran_v3", "name": "龙安燃", "gender": "女", "age": "30-40", "trait": "活泼质感", "instruct": False, "lang": "中/英"},
        {"id": "longanxuan_v3", "name": "龙安宣", "gender": "女", "age": "30-40", "trait": "经典直播", "instruct": False, "lang": "中/英"},
    ]},
    {"category": "女声·老年(55+)", "voices": [
        {"id": "longlaoyi_v3", "name": "龙老姨", "gender": "女", "age": "60+", "trait": "烟火从容阿姨", "instruct": False, "lang": "中/英"},
    ]},
    {"category": "童声·少年(5-18)", "voices": [
        {"id": "longhuhu_v3", "name": "龙呼呼", "gender": "女", "age": "6-10", "trait": "天真烂漫女童", "instruct": True, "lang": "中/英"},
        {"id": "longjielidou_v3", "name": "龙杰力豆", "gender": "男", "age": "10", "trait": "阳光顽皮男童", "instruct": False, "lang": "中/英"},
        {"id": "longniuniu_v3", "name": "龙牛牛", "gender": "男", "age": "6-15", "trait": "阳光男童", "instruct": False, "lang": "中/英"},
        {"id": "longshanshan_v3", "name": "龙闪闪", "gender": "女", "age": "6-15", "trait": "戏剧化童声", "instruct": False, "lang": "中/英"},
        {"id": "longling_v3", "name": "龙铃", "gender": "女", "age": "10", "trait": "稚气呆板女童", "instruct": False, "lang": "中/英"},
        {"id": "longxian_v3", "name": "龙仙", "gender": "女", "age": "12", "trait": "豪放可爱女童", "instruct": False, "lang": "中/英"},
        {"id": "longpaopao_v3", "name": "龙泡泡", "gender": "女", "age": "6-15", "trait": "飞天泡泡音", "instruct": False, "lang": "中/英"},
        {"id": "longdaiyu_v3", "name": "龙黛玉", "gender": "女", "age": "15-25", "trait": "娇率才女·古风", "instruct": False, "lang": "中/英"},
    ]},
    {"category": "旁白·解说", "voices": [
        {"id": "longmiao_v3", "name": "龙妙", "gender": "女", "age": "25-30", "trait": "抑扬顿挫·旁白", "instruct": False, "lang": "中/英"},
        {"id": "loongbella_v3", "name": "Bella3.0", "gender": "女", "age": "25-30", "trait": "精准干练·播报", "instruct": False, "lang": "中/英"},
    ]},
    {"category": "方言", "voices": [
        {"id": "longanhuan_v3", "name": "龙安欢(方言)", "gender": "女", "age": "20-30", "trait": "欢脱元气·多方言", "instruct": True, "lang": "粤/东北/川/鲁等"},
        {"id": "longanyue_v3", "name": "龙安粤", "gender": "男", "age": "25-35", "trait": "欢脱粤语", "instruct": False, "lang": "粤语"},
        {"id": "longjiaxin_v3", "name": "龙嘉欣", "gender": "女", "age": "30-35", "trait": "优雅粤语", "instruct": False, "lang": "粤语"},
        {"id": "longjiayi_v3", "name": "龙嘉怡", "gender": "女", "age": "25-30", "trait": "知性粤语", "instruct": False, "lang": "粤语"},
        {"id": "longlaotie_v3", "name": "龙老铁", "gender": "男", "age": "25-30", "trait": "东北直率", "instruct": False, "lang": "东北话"},
        {"id": "longshange_v3", "name": "龙陕哥", "gender": "男", "age": "25-35", "trait": "原味陕北", "instruct": False, "lang": "陕西话"},
        {"id": "longanmin_v3", "name": "龙安闽", "gender": "女", "age": "18-25", "trait": "清纯闽南", "instruct": False, "lang": "闽南话"},
    ]},
    {"category": "特色", "voices": [
        {"id": "longhouge_v3", "name": "龙猴哥", "gender": "男", "age": "20-25", "trait": "经典猴哥", "instruct": False, "lang": "中/英"},
        {"id": "longjiqi_v3", "name": "龙机器", "gender": "男", "age": "20-30", "trait": "呆萌机器人", "instruct": False, "lang": "中/英"},
    ]},
    {"category": "外语·英语", "voices": [
        {"id": "loongandy_v3", "name": "Andy", "gender": "男", "age": "30-35", "trait": "美式英文男", "instruct": False, "lang": "英语"},
        {"id": "loongdavid_v3", "name": "David", "gender": "男", "age": "35-40", "trait": "美式英文男", "instruct": False, "lang": "英语"},
        {"id": "loongeric_v3", "name": "Eric", "gender": "男", "age": "35-40", "trait": "英式英文男", "instruct": False, "lang": "英语"},
        {"id": "loongluca_v3", "name": "Luca", "gender": "男", "age": "25-30", "trait": "英式英文男", "instruct": False, "lang": "英语"},
        {"id": "loongabby_v3", "name": "Abby", "gender": "女", "age": "30-35", "trait": "美式英文女", "instruct": False, "lang": "英语"},
        {"id": "loongannie_v3", "name": "Annie", "gender": "女", "age": "30-35", "trait": "美式英文女", "instruct": False, "lang": "英语"},
        {"id": "loongava_v3", "name": "Ava", "gender": "女", "age": "35-40", "trait": "美式英文女", "instruct": False, "lang": "英语"},
        {"id": "loongbeth_v3", "name": "Beth", "gender": "女", "age": "35-40", "trait": "美式英文女", "instruct": False, "lang": "英语"},
        {"id": "loongcally_v3", "name": "Cally", "gender": "女", "age": "25-30", "trait": "美式英文女", "instruct": False, "lang": "英语"},
        {"id": "loongcindy_v3", "name": "Cindy", "gender": "女", "age": "30-35", "trait": "美式英文女", "instruct": False, "lang": "英语"},
        {"id": "loongdonna_v3", "name": "Donna", "gender": "女", "age": "35-40", "trait": "美式英文女", "instruct": False, "lang": "英语"},
        {"id": "loongemily_v3", "name": "Emily", "gender": "女", "age": "35-40", "trait": "英式英文女", "instruct": False, "lang": "英语"},
        {"id": "loongluna_v3", "name": "Luna", "gender": "女", "age": "35-40", "trait": "英式英文女", "instruct": False, "lang": "英语"},
    ]},
    {"category": "外语·日韩及其他", "voices": [
        {"id": "loongriko_v3", "name": "Riko", "gender": "女", "age": "18-25", "trait": "二次元日语女", "instruct": False, "lang": "日语"},
        {"id": "loongtomoka_v3", "name": "Tomoka", "gender": "女", "age": "30-35", "trait": "日语女", "instruct": False, "lang": "日语"},
        {"id": "loongtomoya_v3", "name": "Tomoya", "gender": "男", "age": "30-35", "trait": "日语男", "instruct": False, "lang": "日语"},
        {"id": "loongyuuna_v3", "name": "Yuuna", "gender": "女", "age": "18-25", "trait": "日语女", "instruct": False, "lang": "日语"},
        {"id": "loongyuuma_v3", "name": "Yuuma", "gender": "男", "age": "20-25", "trait": "日语男", "instruct": False, "lang": "日语"},
        {"id": "loongkyong_v3", "name": "Kyong", "gender": "女", "age": "25-30", "trait": "韩语女", "instruct": False, "lang": "韩语"},
        {"id": "loongjihun_v3", "name": "Jihun", "gender": "男", "age": "25-30", "trait": "韩语男", "instruct": False, "lang": "韩语"},
        {"id": "loongindah_v3", "name": "Indah", "gender": "女", "age": "22-27", "trait": "印尼语女", "instruct": False, "lang": "印尼语"},
    ]},
]

# id -> 音色元信息（快速查找）
VOICES_BY_ID = {v["id"]: v
                for grp in VOICE_LIBRARY for v in grp["voices"]}


def voice_supports_instruct(voice_id: str) -> bool:
    """该音色是否支持情感指令(Instruct)。未知音色保守返回 False。"""
    return bool(VOICES_BY_ID.get((voice_id or "").strip(), {}).get("instruct"))


def voice_meta(voice_id: str) -> dict:
    return VOICES_BY_ID.get((voice_id or "").strip(), {})


def voice_options() -> dict:
    """给前端：分类音色库 + 情感选项 + 参数范围 + 默认值。"""
    return {
        "library": VOICE_LIBRARY,
        "emotions": [{"value": k, "label": v} for k, v in EMOTIONS.items()],
        "ranges": {"speech_rate": [0.5, 2.0], "pitch_rate": [0.5, 2.0],
                   "volume": [0, 100]},
        "defaults": {"voice": COSYVOICE_DEFAULT_VOICE, "model": COSYVOICE_MODEL,
                     "speech_rate": COSYVOICE_DEFAULT_SPEECH_RATE,
                     "pitch_rate": COSYVOICE_DEFAULT_PITCH_RATE,
                     "volume": COSYVOICE_DEFAULT_VOLUME},
    }


# ── 参数规整 ──────────────────────────────────────────────
def _clamp(v, default, lo, hi) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        f = float(default)
    return max(lo, min(hi, f))


def normalize_voice_config(raw: dict) -> dict:
    """把角色/单句的声音配置规整为可直接喂给 synthesize 的参数字典。

    - voice 缺省用默认音色；model 缺省用默认模型；
    - 情感仅对支持 Instruct 的音色保留，否则置空（避免无效指令）；
    - 语速/音调/音量夹取到官方范围。
    """
    raw = raw or {}
    voice = str(raw.get("voice") or "").strip() or COSYVOICE_DEFAULT_VOICE
    emo = normalize_emotion(raw.get("emotion"))
    if emo and not voice_supports_instruct(voice):
        emo = ""                       # 该音色不支持情感指令 → 降级
    seed = raw.get("seed")
    try:
        seed = int(seed) if str(seed).strip() not in ("", "None") else None
    except (TypeError, ValueError):
        seed = None
    return {
        "voice": voice,
        "model": str(raw.get("model") or "").strip() or COSYVOICE_MODEL,
        "emotion": emo,
        "scene": str(raw.get("scene") or "").strip(),
        "role": str(raw.get("role") or "").strip(),
        "speech_rate": _clamp(raw.get("speech_rate"), COSYVOICE_DEFAULT_SPEECH_RATE, 0.5, 2.0),
        "pitch_rate": _clamp(raw.get("pitch_rate"), COSYVOICE_DEFAULT_PITCH_RATE, 0.5, 2.0),
        "volume": int(_clamp(raw.get("volume"), COSYVOICE_DEFAULT_VOLUME, 0, 100)),
        "seed": seed,
        "language": str(raw.get("language") or "").strip(),
    }


# ── CosyVoice SDK（延迟导入，未安装时给清晰提示，不影响应用启动）──────
def _load_sdk():
    try:
        import dashscope
        from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat
        return dashscope, SpeechSynthesizer, AudioFormat
    except ImportError as e:
        raise RuntimeError("未安装 dashscope SDK，无法配音。请在 v6 环境执行："
                           "pip install \"dashscope>=1.26.4\"") from e


def _audio_format(AudioFormat):
    """按 COSYVOICE_FORMAT 选枚举；名字对不上时回退默认 MP3。"""
    f = (COSYVOICE_FORMAT or "mp3").lower()
    name = {"mp3": "MP3_22050HZ_MONO_256KBPS",
            "wav": "WAV_22050HZ_MONO_16BIT",
            "pcm": "PCM_22050HZ_MONO_16BIT"}.get(f, "MP3_22050HZ_MONO_256KBPS")
    return getattr(AudioFormat, name, AudioFormat.MP3_22050HZ_MONO_256KBPS)


def synthesize(text: str, out_path, voice: str = None, model: str = None,
               emotion: str = None, scene: str = "", role: str = "",
               speech_rate=None, pitch_rate=None, volume=None, seed=None,
               language: str = "", instruction: str = None) -> str:
    """合成一句配音并写入 out_path，返回文件路径（同步阻塞，路由层用 to_thread）。

    每次调用都重新初始化 SpeechSynthesizer（官方要求）。情感仅对支持 Instruct
    的音色生效；未支持时 emotion 被忽略（由 pitch/rate/volume 近似表达情绪）。
    """
    text = (text or "").strip()
    if not text:
        raise RuntimeError("配音文本为空")
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("未配置 SCRIPT_TOOL_DASHSCOPE_API_KEY，无法配音")

    dashscope, SpeechSynthesizer, AudioFormat = _load_sdk()
    dashscope.api_key = DASHSCOPE_API_KEY
    if COSYVOICE_WS_URL:
        dashscope.base_websocket_api_url = COSYVOICE_WS_URL

    cfg = normalize_voice_config({
        "voice": voice, "model": model, "emotion": emotion, "scene": scene,
        "role": role, "speech_rate": speech_rate, "pitch_rate": pitch_rate,
        "volume": volume, "seed": seed, "language": language})

    kwargs = dict(model=cfg["model"], voice=cfg["voice"],
                  format=_audio_format(AudioFormat),
                  volume=cfg["volume"], speech_rate=cfg["speech_rate"],
                  pitch_rate=cfg["pitch_rate"])
    instr = instruction or build_instruction(cfg["emotion"], cfg["scene"], cfg["role"])
    if instr and voice_supports_instruct(cfg["voice"]):
        kwargs["instruction"] = instr
    if cfg["seed"] is not None:
        kwargs["seed"] = cfg["seed"]
    if cfg["language"]:
        kwargs["language_hints"] = [cfg["language"]]

    synth = SpeechSynthesizer(**kwargs)
    audio = synth.call(text)
    if not audio:
        rid = ""
        try:
            rid = synth.get_last_request_id()
        except Exception:
            pass
        raise RuntimeError(f"语音合成返回空音频（voice={cfg['voice']}, "
                           f"model={cfg['model']}, requestId={rid}）")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    return str(out)


def probe_audio_duration(path) -> float:
    """读取音频/视频时长（秒），失败返回 0（复用 subtitles 的实现）。"""
    from app.media.subtitles import probe_duration
    return probe_duration(path)


# ── 音画混流：把多段配音按时间轴混入（无声）视频 ──────────────
def mux_voice_to_video(video_path, segments: list, out_path=None) -> str:
    """把配音片段按 start 秒混入视频，返回输出视频路径（同步阻塞）。

    segments: [{"audio": 本地音频路径, "start": 起始秒}]
    - 各段用 adelay 定位到时间轴，amix(normalize=0) 保持原音量混合；
    - 视频流直接 copy（不重编码，快且无损），音频编码为 aac；
    - 输出时长以视频为准（-t 视频时长），配音超出部分被截断。
    所有片段需与视频同目录（用相对文件名，规避 Windows 路径转义问题）。
    """
    segs = [s for s in (segments or [])
            if s.get("audio") and Path(s["audio"]).exists()]
    if not segs:
        return str(video_path)
    exe = _ffmpeg_exe()
    vp = Path(video_path)
    out = Path(out_path) if out_path else vp.with_name(vp.stem + "_voiced.mp4")

    inputs = ["-i", vp.name]
    parts, labels = [], []
    for i, s in enumerate(segs, start=1):
        inputs += ["-i", Path(s["audio"]).name]
        ms = int(max(0.0, float(s.get("start") or 0.0)) * 1000)
        parts.append(f"[{i}:a]adelay={ms}|{ms}[a{i}]")
        labels.append(f"[a{i}]")
    fc = (";".join(parts) + ";" + "".join(labels)
          + f"amix=inputs={len(segs)}:duration=longest:normalize=0[aout]")

    from app.media.subtitles import probe_duration
    dur = probe_duration(vp)
    cmd = [exe, "-y", *inputs, "-filter_complex", fc,
           "-map", "0:v", "-map", "[aout]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    if dur > 0:
        cmd += ["-t", f"{dur:.2f}"]
    cmd += [out.name]
    try:
        proc = subprocess.run(cmd, cwd=str(vp.parent), capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("未找到 ffmpeg：请安装 imageio-ffmpeg（pip install imageio-ffmpeg）")
    if proc.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"配音混流失败：{(proc.stderr or '')[-400:]}")
    return str(out)
