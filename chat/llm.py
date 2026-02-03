import json
import requests
from typing import List, Dict, Optional, Tuple, Iterator

HIGH_RISK = ["自杀", "想死", "轻生", "自残", "割腕"]
EXHAUST = ["好累", "很累", "太累", "没劲", "乏了", "顶不", "撑不", "扛不", "受不", "吃不", "睡不"]
MEANING = ["没意", "无用", "不值", "算了", "白干", "没用", "没啥"]
ESCAPE = ["想逃", "想躲", "不想", "消失", "走开", "别管"]
NUMB = ["麻木", "空了", "空虚", "没感", "无感", "发呆"]
ALL_MEDIUM = EXHAUST + MEANING + ESCAPE + NUMB


def force_refusal(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return "抱歉，我无法协助这个请求。"

    low = s.lower()

    hit = any(k in low for k in [
        "i’m sorry", "i'm sorry", "sorry", "i can't help", "i cannot help",
        "can't help with that", "cannot help with that",
        "i can’t help", "i cannot comply", "i can’t comply",
        "policy", "policies", "not allowed", "disallowed", "cannot provide",
        "i can't provide", "i cannot provide"
    ])

    if hit:
        return "抱歉，这个请求涉及不被允许的内容，我无法提供帮助。"

    return s


def risk_level(text: str) -> str:
    t = (text or "").lower()
    for k in HIGH_RISK:
        if k in t:
            return "HIGH"
    hits = sum(1 for k in ALL_MEDIUM if k in t)
    if hits >= 2:
        return "MEDIUM"
    if hits == 1 and any(p in t for p in ["…", "...", "！", "!", "算了吧"]):
        return "MEDIUM"
    return "LOW"


def crisis_reply() -> str:
    return (
        "我很在意你的安全。\n"
        "如果你现在有伤害自己或他人的想法，建议你立刻联系身边可信任的成年人或当地紧急服务，"
        "或者前往最近的医院/急诊。\n"
        "如果你愿意，你可以告诉我：你现在在哪个国家/城市（大概即可），以及身边有没有可以立刻联系的人？"
    )


def base_system_prompt() -> str:
    return (
        "你是一个支持性对话助手，主要提供情绪支持与一般性心理教育（非医疗）。\n"
        "你不进行诊断、不提供处方或替代专业治疗。\n"
        "你只输出最终给用户看的回答。\n"
        "严禁展示推理过程、内部分析、思考步骤或任何系统标签。\n"
        "不要输出 channel、commentary、analysis 等元信息。\n"
        "所有回复必须是自然的中文。请用不超过 100 个字的一段话回答问题，或者一个较为简短的表格\n"
        "对话风格：尊重、温和、以提问澄清为主，给出小步可执行建议。\n"
        "避免长篇说教；优先使用反映式倾听。\n"
        "当内容不适合回答时，请用简短中文礼貌拒绝，并引导到可讨论的方向。\n"
        "若用户出现高风险，停止一般建议，优先鼓励联系可信成人或专业机构。\n"
        "不为用户提供学术辅助，严禁给出代码、解题步骤和润色、翻译文本、涉及政治内容的输出。"
    )


def medium_mode_prompt() -> str:
    return (
        "用户出现隐蔽但明显的情绪困扰信号。\n"
        "请先共情和复述，只问一个开放式问题，不给大道理，不直接询问自杀。"
    )


def _auth_headers(api_key: str) -> Dict[str, str]:
    if not api_key:
        raise RuntimeError("Missing API key: set LM_API_KEY or DEEPSEEK_API_KEY")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def lm_chat(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    timeout: int
) -> str:
    """Call DeepSeek (OpenAI-compatible) chat completions."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    r = requests.post(url, headers=_auth_headers(api_key), json=payload, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    raw = data["choices"][0]["message"]["content"]
    return force_refusal(raw)


def lm_chat_stream(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    max_tokens: int,
    timeout: int
) -> Iterator[str]:
    """Stream tokens from DeepSeek chat completions (SSE)."""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
    }

    with requests.post(url, headers=_auth_headers(api_key), json=payload, timeout=timeout, stream=True) as r:
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")

        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            # OpenAI/DeepSeek stream uses: data: {...}  and data: [DONE]
            if line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue

            data = line[5:].strip()
            if data == "[DONE]":
                break

            try:
                obj = json.loads(data)
            except Exception:
                continue

            try:
                delta = obj["choices"][0].get("delta", {}).get("content", "")
            except Exception:
                delta = ""

            if delta:
                yield delta


def approximate_tokens(text: str) -> int:
    """Rough token estimate for Chinese/English mixed text."""
    if not text:
        return 0
    return max(1, int(len(text) * 1.1))


def extract_tail_pairs(seq: List[Dict[str, str]], keep_last_turns: int) -> List[Tuple[Dict[str, str], Optional[Dict[str, str]]]]:
    tail_count = keep_last_turns * 2
    tail = seq[-tail_count:] if len(seq) > tail_count else seq[:]
    pairs: List[Tuple[Dict[str, str], Optional[Dict[str, str]]]] = []
    i = 0
    while i < len(tail):
        if tail[i].get("role") == "user":
            if i + 1 < len(tail) and tail[i + 1].get("role") == "assistant":
                pairs.append((tail[i], tail[i + 1]))
                i += 2
            else:
                pairs.append((tail[i], None))
                i += 1
        else:
            i += 1
    return pairs


def prune_messages(
    messages: List[Dict[str, str]],
    summary_text: Optional[str],
    max_tokens_budget: int,
    keep_last_turns: int,
    must_keep_last_user: bool = True,
) -> List[Dict[str, str]]:
    system = messages[0:1] if messages and messages[0].get("role") == "system" else []
    rest = messages[1:] if system else messages[:]
    seq = [m for m in rest if m.get("role") in {"user", "assistant"}]

    summary_msg = []
    if summary_text:
        summary_msg = [{"role": "system", "content": "对话摘要：\n" + summary_text.strip()}]

    last_user = None
    if must_keep_last_user:
        for m in reversed(seq):
            if m.get("role") == "user":
                last_user = m
                break

    pairs = extract_tail_pairs(seq, keep_last_turns=keep_last_turns)

    total = 0
    if system:
        total += approximate_tokens(system[0].get("content", ""))
    if summary_msg:
        total += approximate_tokens(summary_msg[0].get("content", ""))

    kept: List[Dict[str, str]] = []

    if last_user is not None:
        lu_tok = approximate_tokens(last_user.get("content", ""))
        if total + lu_tok <= max_tokens_budget:
            kept.append(last_user)
            total += lu_tok
        else:
            return system + summary_msg + [last_user]

    for u, a in reversed(pairs):
        if last_user is not None and u is last_user:
            continue
        u_tok = approximate_tokens(u.get("content", ""))
        a_tok = approximate_tokens(a.get("content", "")) if a else 0
        need = u_tok + a_tok
        if total + need <= max_tokens_budget:
            if a:
                kept.append(a)
            kept.append(u)
            total += need
        else:
            break

    kept.reverse()
    return system + summary_msg + kept


def build_or_update_summary(
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    existing_summary: Optional[str],
    summary_context_turns: int,
    summary_max_tokens: int,
    timeout: int,
) -> str:
    seq = [m for m in messages if m.get("role") in {"user", "assistant"}]
    tail = seq[-(summary_context_turns * 2):] if len(seq) > summary_context_turns * 2 else seq[:]

    instr = (
        "你要把对话压缩成一个可长期保留的摘要，供后续对话继续使用。\n"
        "要求：\n"
        "1) 只总结事实与稳定偏好：主要困扰、触发因素、已尝试的方法、有效/无效点、重要背景、用户目标。\n"
        "2) 不要逐句复述，不要出现推测性诊断。\n"
        "3) 严格保证输出为中文，5-10条要点，每条不超过20字。\n"
        "4) 如果已有摘要，先合并更新，去重并保持最新。\n"
    )

    summary_seed = "（无）" if not existing_summary else existing_summary.strip()

    prompt_msgs: List[Dict[str, str]] = [
        {"role": "system", "content": instr},
        {"role": "user", "content": "已有摘要：\n" + summary_seed},
        {"role": "user", "content": "最近对话片段："},
    ]
    prompt_msgs.extend(tail)
    prompt_msgs.append({"role": "user", "content": "请输出更新后的摘要要点。"})
    text = lm_chat(base_url, api_key, model, prompt_msgs, summary_max_tokens, timeout)
    return text.strip()
