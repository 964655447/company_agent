from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..local_rules import wf4_fallback, wf5_fallback
from ..models import AssessmentLog, AssessmentStat, Employee
from ..security import get_current_user, require_manager

router = APIRouter(prefix="/api/assessment", tags=["进阶考核"])


def _assess_period_range(period: str, target_month: str | None):
    """考核周期 → (start, end)，基于 test_time / created_at 过滤。"""
    today = date.today()
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return start, today
    if period == "month":
        return today.replace(day=1), today
    if period == "last_month":
        first_this = today.replace(day=1)
        end_last = first_this - timedelta(days=1)
        return end_last.replace(day=1), end_last
    if period == "all":
        return None, None
    if period == "specific" and target_month and len(target_month) == 7:
        y, m = target_month.split("-")
        first = date(int(y), int(m), 1)
        last = (first.replace(month=int(m) + 1) - timedelta(days=1)) if int(m) < 12 else \
              first.replace(year=first.year + 1, month=1) - timedelta(days=1)
        return first, last
    return today.replace(day=1), today


class QueryIn(BaseModel):
    position: str


@router.post("/query")
async def query_position(body: QueryIn,
                         user: Employee = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    position = body.position.strip()
    if not position:
        return {"intro": "请输入想了解的岗位名称"}
    result = wf4_fallback(position)
    # 结合实际数据：当前在岗人数 + 本人对该岗位的历史成绩
    holders = db.scalars(select(Employee).where(Employee.position == position)).all()
    result["holders_count"] = len(holders)
    my_stats = db.scalars(select(AssessmentStat).where(
        AssessmentStat.employee_id == user.employee_id,
        AssessmentStat.target_position == position,
    )).all()
    valid = [s.score for s in my_stats if s.score is not None]
    result["my_score"] = round(max(valid), 1) if valid else None
    db.add(AssessmentLog(employee_id=user.employee_id, position_queried=position))
    db.commit()
    return result


@router.get("/stats")
def stats(
    period: str = Query("month", pattern="^(week|month|last_month|all|specific)$"),
    target_month: str | None = Query(None),
    manager: Employee = Depends(require_manager),
    db: Session = Depends(get_db),
):
    start, end = _assess_period_range(period, target_month)
    q = select(AssessmentLog.position_queried, Employee.name, func.count(AssessmentLog.id)) \
        .join(Employee, AssessmentLog.employee_id == Employee.employee_id)
    if start:
        q = q.where(AssessmentLog.created_at >= datetime.combine(start, time.min))
    if end:
        q = q.where(AssessmentLog.created_at <= datetime.combine(end, time.max))
    rows = db.execute(
        q.group_by(AssessmentLog.position_queried, Employee.name)
         .order_by(func.count(AssessmentLog.id).desc())
    ).all()
    return {
        "rows": [{"name": r[1], "position_queried": r[0], "count": r[2]} for r in rows],
        "range_start": str(start) if start else "",
        "range_end": str(end) if end else "",
    }


@router.get("/scores")
def my_scores(
    period: str = Query("month", pattern="^(week|month|last_month|all|specific)$"),
    target_month: str | None = Query(None),
    user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """本人考核成绩（原岗位 / 意向岗位 / 成绩 / 测试时间）。"""
    start, end = _assess_period_range(period, target_month)
    q = select(AssessmentStat, Employee.name) \
        .join(Employee, AssessmentStat.employee_id == Employee.employee_id) \
        .where(AssessmentStat.employee_id == user.employee_id)
    if start:
        q = q.where(AssessmentStat.test_time >= datetime.combine(start, time.min))
    if end:
        q = q.where(AssessmentStat.test_time <= datetime.combine(end, time.max))
    rows = db.execute(q.order_by(AssessmentStat.test_time.desc())).all()
    return {
        "scores": [{"name": r[1], **r[0].to_dict()} for r in rows],
        "range_start": str(start) if start else "",
        "range_end": str(end) if end else "",
    }


@router.get("/scores/all")
def all_scores(
    period: str = Query("month", pattern="^(week|month|last_month|all|specific)$"),
    target_month: str | None = Query(None),
    manager: Employee = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """管理员：全员考核成绩汇总（按工号、测试时间倒序）。"""
    start, end = _assess_period_range(period, target_month)
    q = select(AssessmentStat, Employee.name) \
        .join(Employee, AssessmentStat.employee_id == Employee.employee_id)
    if start:
        q = q.where(AssessmentStat.test_time >= datetime.combine(start, time.min))
    if end:
        q = q.where(AssessmentStat.test_time <= datetime.combine(end, time.max))
    rows = db.execute(q.order_by(AssessmentStat.employee_id, AssessmentStat.test_time.desc())).all()
    return {
        "scores": [{"name": r[1], **r[0].to_dict()} for r in rows],
        "range_start": str(start) if start else "",
        "range_end": str(end) if end else "",
    }


# ============================================================
# 考核出题 + 答题提交（申请考核完整流程）
# ============================================================

class GenerateIn(BaseModel):
    target_position: str


class AnswerItem(BaseModel):
    question_id: int
    user_answer: list[int]  # 用户选中的选项索引列表（单选也用 list，长度=1）


class SubmitIn(BaseModel):
    target_position: str
    original_position: str = ""
    answers: list[AnswerItem]


@router.post("/generate")
async def generate_quiz(
    body: GenerateIn,
    user: Employee = Depends(get_current_user),
):
    """为指定岗位生成考核试题。优先调 Dify 工作流，降级本地模板。"""
    pos = body.target_position.strip()
    if not pos:
        return {"error": "请选择目标岗位", "questions": []}

    # TODO: Dify 接通后替换为 call_dify_workflow("job_description and test_generation", ...)
    # 当前使用本地 fallback
    result = wf5_fallback(pos)

    return {
        "target_position": pos,
        "total_questions": result["total_questions"],
        "max_score": result["max_score"],
        "questions": result["questions"],
        "source": result.get("source", "local_fallback"),
    }


@router.post("/submit")
async def submit_quiz(
    body: SubmitIn,
    user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """提交答卷 → 本地打分 → 写入 AssessmentStat 表 → 返回成绩单。"""
    pos = body.target_position.strip()
    orig_pos = body.original_position.strip() or user.position

    if not body.answers:
        return {"error": "答卷不能为空", "score": None}

    # 重新生成该岗位的标准答案（与 generate 一致）
    standard = wf5_fallback(pos)
    answer_map = {q["id"]: q for q in standard["questions"]}

    breakdown = []
    total = 0.0
    single_total = 0.0
    multi_total = 0.0
    judge_total = 0.0

    for ans_item in body.answers:
        qid = ans_item.question_id
        std_q = answer_map.get(qid)
        if not std_q:
            continue

        user_ans = ans_item.user_answer or []
        correct_ans = std_q["answer"]
        pts = std_q["points"]
        qtype = std_q["type"]

        if qtype == "single":
            earned = pts if user_ans and user_ans[0] == correct_ans else 0
            single_total += earned
        elif qtype == "multi":
            if not user_ans or set(user_ans) - set(correct_ans):
                earned = 0
            elif set(user_ans) == set(correct_ans):
                earned = pts
            else:
                earned = round(len(set(user_ans) & set(correct_ans)) * (pts / len(correct_ans)), 2)
            multi_total += earned
        elif qtype == "judge":
            earned = pts if user_ans and user_ans[0] == correct_ans else 0
            judge_total += earned
        else:
            earned = 0

        total += earned
        breakdown.append({
            "question_id": qid,
            "type": qtype,
            "question": std_q["question"],
            "user_answer": user_ans,
            "correct_answer": correct_ans,
            "points": pts,
            "earned": earned,
            "is_correct": earned == pts,
        })

    total = round(total, 1)
    band = "优秀" if total >= 90 else "良好" if total >= 80 else "合格" if total >= 60 else "待提升"

    stat = AssessmentStat(
        employee_id=user.employee_id,
        original_position=orig_pos,
        target_position=pos,
        score=total,
        test_time=datetime.now(),
    )
    db.add(stat)
    db.commit()

    return {
        "score": total,
        "band": band,
        "max_score": 100,
        "single_score": round(single_total, 1),
        "multi_score": round(multi_total, 1),
        "judge_score": round(judge_total, 1),
        "breakdown": breakdown,
        "original_position": orig_pos,
        "target_position": pos,
        "test_time": stat.test_time.isoformat() if stat.test_time else None,
    }
