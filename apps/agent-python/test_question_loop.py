"""Random question testing loop for Evidence-first Travel Intelligence Agent.

Randomly selects questions from Question.txt, tests them against the agent,
and iterates until 2 consecutive questions produce satisfactory answers.
"""

import asyncio
import random
import re
import sys
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent
QUESTION_FILE = PROJECT_ROOT.parent.parent / "Question.txt"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent.parent / "packages"))


def parse_questions(filepath: str) -> list[str]:
    """Extract actual questions from Question.txt, filtering headers and blank lines."""
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    questions = []
    # Section header patterns
    header_patterns = [
        r"^出发前随手搜", r"^查票价", r"^做路线规划时会问",
        r"^担心踩坑时会问", r"^查季节和天气时会问", r"^查评论体验时会问",
        r"^临出门前会问", r"^在当地边走边问", r"^多轮续聊会这样问",
        r"^更像真实用户的核心问题",
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip section headers
        is_header = False
        for pattern in header_patterns:
            if re.match(pattern, stripped):
                is_header = True
                break
        if is_header:
            continue
        # Skip meta-descriptions (lines starting with 值不值得去, 会不会踩坑, etc. that look like summaries)
        if re.match(r"^(值不值得去|会不会踩坑|贵不贵|累不累|人多不多|怎么去|几月份|带老人|附近吃住|今天/明天)", stripped):
            continue
        # Must contain a question mark or be a substantive query
        questions.append(stripped)

    return questions


def evaluate_answer(question: str, response) -> tuple[bool, str, dict]:
    """Evaluate whether a response satisfactorily answers the question.

    Returns (passed, reason, metrics).
    """
    answer = response.answer if hasattr(response, 'answer') else str(response)
    confidence = response.confidence if hasattr(response, 'confidence') else 0.0
    limitations = response.limitations if hasattr(response, 'limitations') else []
    structured = response.structured_result if hasattr(response, 'structured_result') else None
    evidence = response.evidence_summary if hasattr(response, 'evidence_summary') else []

    metrics = {
        "answer_len": len(answer),
        "confidence": confidence,
        "limitations_count": len(limitations),
        "evidence_count": len(evidence),
    }

    # CRITICAL FAIL: No answer at all
    if not answer or len(answer) < 20:
        return False, "答案为空或过短(<20字符)", metrics

    # CRITICAL FAIL: Error message in answer
    error_markers = ["暂无法理解", "暂不支持", "无法处理", "系统错误", "internal error"]
    for marker in error_markers:
        if marker in answer:
            return False, f"答案包含错误标记: {marker}", metrics

    # Check if answer is substantive vs just disclaimers
    substantive_content = answer
    disclaimer_phrases = [
        "该问题超出", "无法确认", "建议查阅官方", "建议前往官方",
        "暂无相关数据", "暂无足够证据", "暂时无法回答", "信息不足",
        "建议直接查询", "请参考官方", "建议通过官方渠道",
    ]
    disclaimer_count = sum(1 for phrase in disclaimer_phrases if phrase in substantive_content)

    # If >50% of the answer is disclaimers, it's not helpful
    if disclaimer_count >= 3 and len(answer) < 300:
        return False, "回答以免责声明为主，实质性内容不足", metrics

    # Confidence too low
    if confidence < 0.15:
        return False, f"置信度过低({confidence:.2f})", metrics

    # Check question-type-specific quality
    passed, reason = check_question_specific_quality(question, answer, response, metrics)
    if not passed:
        return False, reason, metrics

    # Overall quality check
    if len(answer) < 80:
        return False, "答案长度不足(<80字符)，可能内容不够丰富", metrics

    return True, "OK", metrics


def check_question_specific_quality(question: str, answer: str, response, metrics: dict) -> tuple[bool, str]:
    """Check question-type-specific answer quality."""
    answer_lower = answer.lower()

    # Fact lookup: ticket price
    if any(kw in question for kw in ["门票", "票价", "多少钱", "贵不贵", "贵吗"]):
        price_patterns = [r"\d+元", r"\d+\s*CNY", r"\d+\s*JPY", r"\d+\s*KRW", r"\d+\s*人民币",
                          r"免费", r"free", r"\$\d+", r"\d+块钱"]
        has_price = any(re.search(p, answer) for p in price_patterns)
        if not has_price:
            return False, "票价问题但答案中未找到价格信息", metrics
        return True, "OK"

    # Fact lookup: opening hours
    if any(kw in question for kw in ["几点关门", "几点开门", "开放时间", "开门", "关门时间", "开放吗", "还能进去吗"]):
        time_patterns = [r"\d{1,2}:\d{2}", r"\d{1,2}点", r"全天", r"24小时", r"开放", r"不开放"]
        has_time = any(re.search(p, answer) for p in time_patterns)
        if not has_time:
            return False, "开放时间问题但答案中未找到时间信息", metrics
        return True, "OK"

    # Comparison
    if any(kw in question for kw in ["哪个更", "还是", "选哪个", "只能选一个", "和.*比", "差很多"]):
        if len(answer) < 100:
            return False, "比较类问题答案过短", metrics
        return True, "OK"

    # Suitability for elderly
    if any(kw in question for kw in ["老人", "父母", "长辈", "爸妈", "带老"]):
        elderly_keywords = ["步行", "走路", "爬", "坡", "累", "休息", "台阶", "电梯", "设施", "适合老人",
                            "walking", "elderly", "senior", "rest", "steep"]
        has_elderly_info = any(kw in answer_lower for kw in elderly_keywords)
        if not has_elderly_info:
            return False, "老人适老化问题但答案未涉及相关因素", metrics
        return True, "OK"

    # Weather
    if any(kw in question for kw in ["天气", "冷", "热", "下雨", "下雨天", "冷不冷", "热不热"]):
        weather_keywords = ["温度", "度", "°", "天气", "雨", "晴", "阴", "雪", "风", "冷", "热",
                            "temperature", "weather", "rain", "sunny", "cloudy", "cold", "hot"]
        has_weather = any(kw in answer_lower for kw in weather_keywords)
        if not has_weather:
            return False, "天气问题但答案未涉及天气信息", metrics
        return True, "OK"

    # Transit/directions
    if any(kw in question for kw in ["怎么去", "怎么走", "交通", "过去", "方便吗", "加油", "开车"]):
        transit_keywords = ["公交", "地铁", "开车", "自驾", "高速", "出租", "巴士", "火车", "站",
                            "bus", "metro", "train", "taxi", "drive", "highway", "station"]
        has_transit = any(kw in answer_lower for kw in transit_keywords)
        if not has_transit:
            return False, "交通问题但答案未涉及出行方式", metrics
        return True, "OK"

    # Food nearby
    if any(kw in question for kw in ["好吃的", "吃的", "吃饭", "餐厅", "吃饭贵", "不坑的餐厅"]):
        food_keywords = ["餐厅", "吃", "美食", "饭店", "小吃", "推荐", "贵", "便宜",
                         "restaurant", "food", "eat", "dining", "cuisine"]
        has_food = any(kw in answer_lower for kw in food_keywords)
        if not has_food:
            return False, "餐饮问题但答案未涉及饮食信息", metrics
        return True, "OK"

    # Crowd level
    if any(kw in question for kw in ["人多", "拥挤", "游客太多", "商业化", "排队", "堵"]):
        crowd_keywords = ["人多", "拥挤", "排队", "游客", "人流", "堵", "高峰",
                          "crowd", "queue", "busy", "tourist", "peak"]
        has_crowd = any(kw in answer_lower for kw in crowd_keywords)
        if not has_crowd:
            return False, "人流问题但答案未涉及拥挤度信息", metrics
        return True, "OK"

    # Season/month
    if any(kw in question for kw in ["几月份", "几月", "季节", "冬天", "夏天", "秋天", "春天", "月份"]):
        season_keywords = ["月", "季节", "春天", "夏天", "秋天", "冬天", "旺季", "淡季",
                           "spring", "summer", "autumn", "fall", "winter", "month", "season",
                           "sep", "oct", "nov", "dec", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug"]
        has_season = any(kw in answer_lower for kw in season_keywords)
        if not has_season:
            return False, "季节问题但答案未涉及时间/月份信息", metrics
        return True, "OK"

    return True, "OK"


async def test_question(question: str) -> tuple[bool, str, dict, object]:
    """Test a single question against the agent."""
    from app.orchestrator.state_machine import TravelAgentStateMachine

    sm = TravelAgentStateMachine()
    try:
        response = await asyncio.wait_for(
            sm.run(question, {}),
            timeout=180.0,
        )
        metrics = {
            "answer": response.answer[:300] + "..." if len(response.answer) > 300 else response.answer,
            "confidence": response.confidence,
            "limitations": response.limitations,
            "evidence_count": len(response.evidence_summary),
            "structured": str(response.structured_result)[:200] if response.structured_result else None,
            "semantic_frame": response.semantic_frame_summary,
        }
        passed, reason, eval_metrics = evaluate_answer(question, response)
        return passed, reason, metrics, response
    except asyncio.TimeoutError:
        return False, "Agent 运行超时(>180s)", {"answer": "TIMEOUT"}, None
    except ValueError as e:
        msg = str(e)
        if "too many values to unpack" in msg:
            return False, "Agent 内部数据格式错误(已知间歇性bug)", {"answer": f"VALUE_ERROR: {msg[:200]}"}, None
        return False, f"Agent 运行异常: ValueError: {msg[:200]}", {"answer": f"ERROR: {e}"}, None
    except Exception as e:
        return False, f"Agent 运行异常: {type(e).__name__}: {str(e)[:200]}", {"answer": f"ERROR: {e}"}, None


def print_separator(char="=", length=80):
    print(char * length)


async def main():
    questions = parse_questions(str(QUESTION_FILE))
    if not questions:
        print("ERROR: No questions found in Question.txt")
        return

    print(f"[INFO] Parsed {len(questions)} questions from Question.txt")
    print_separator()

    consecutive_passes = 0
    total_tested = 0
    total_passed = 0
    round_num = 0
    max_rounds = 50  # Safety limit

    while consecutive_passes < 2 and round_num < max_rounds:
        round_num += 1
        total_tested += 1

        # Randomly select a question
        question = random.choice(questions)
        print(f"\n[ROUND {round_num}] Test (consecutive passes: {consecutive_passes}/2)")
        print(f"[QUESTION] {question}")

        passed, reason, metrics, response = await test_question(question)

        if passed:
            consecutive_passes += 1
            total_passed += 1
            print(f"[PASS] ({reason})")
            print(f"   Confidence: {metrics.get('confidence', 'N/A')}")
            print(f"   Evidence count: {metrics.get('evidence_count', 'N/A')}")
            print(f"   Answer preview: {metrics.get('answer', 'N/A')[:200]}")
        else:
            consecutive_passes = 0
            print(f"[FAIL] {reason}")
            print(f"   Answer preview: {metrics.get('answer', 'N/A')[:200]}")
            if response and hasattr(response, 'limitations'):
                print(f"   Limitations: {response.limitations[:3]}")

    print_separator()
    print(f"\n[SUMMARY]")
    print(f"   Total rounds: {round_num}")
    print(f"   Total questions tested: {total_tested}")
    print(f"   Passed: {total_passed}")
    print(f"   Failed: {total_tested - total_passed}")
    if total_tested > 0:
        print(f"   Pass rate: {total_passed / total_tested * 100:.1f}%")

    if consecutive_passes >= 2:
        print(f"\n[SUCCESS] Achieved {consecutive_passes} consecutive passes!")
    else:
        print(f"\n[STOPPED] Max rounds ({max_rounds}) reached. Final consecutive passes: {consecutive_passes}")


if __name__ == "__main__":
    asyncio.run(main())
