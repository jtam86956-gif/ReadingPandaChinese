"""TTS 音频生成（M0 占位 / 可选能力）。

规划（对应 TECH-STACK §3.3）：
- 用 edge-tts（免费，微软 Edge 神经语音）生成整篇 + 分句朗读 mp3，上传到对象存储
  （Cloudflare R2），manifest 里只存 audio_url（音频不进 Git，控制仓库体积）。
- MVP 阶段可只给「今日推荐」生成音频，其余用阅读器端 Web Speech API 兜底。
- 后期可换 Azure TTS（更自然，含分句时间戳，支持朗读跟读高亮）。

M0 不启用：manifest 的 audio_url 暂为 null。
"""
from __future__ import annotations


def generate_audio(text: str, out_path: str, voice: str = "zh-CN-XiaoxiaoNeural") -> str:
    """生成单段音频并返回可访问 URL。M0 未实现。"""
    raise NotImplementedError(
        "TTS 尚未接通。计划：edge-tts 生成 mp3 → 上传 R2 → 返回 audio_url。"
        "详见 TECH-STACK.md §3.3。"
    )
