"""Readdy 시안의 데모 데이터(부서 3개, 참석자, 지난 회식 기록)를 넣는다.  python -m scripts.seed_demo

사람·가게 이름은 모두 시안과 같은 데모용 이름이다. 실행할 때마다 데모 부서는 처음 상태로 돌아간다.
"""
from app.models import Feedback
from app.store import Store

WHEN = "2026-10-23T19:00:00+09:00"  # 금요일 오후 7시 (시안의 10/24는 토요일이라 금요일로 맞춤)

DEPTS = [
    {"id": "demo", "name": "마케팅팀", "title": "마케팅팀 10월 정기 회식", "lead": "김서연 팀장", "size": 8, "area": "마포·용산",
     "visits": [("hist-m1", "우동 카덴", 4.6, True, 18000, "2026-09-19"),
                ("hist-m2", "라운드 비스트로", 3.8, False, 29000, "2026-08-22"),
                ("hist-m3", "정육식당 한우리", 4.1, True, 27000, "2026-07-25"),
                ("hist-m4", "쌀국수 포레", 4.5, True, 16000, "2026-06-27")],
     "people": [("김서연", "팀장", "신촌", 25000, "없음", "없음", "한식", "조용한 분위기", True),
                ("박지훈", "대리", "이태원", 30000, "없음", "갑각류", "고기", "술 한잔", True),
                ("이하은", "사원", "합정", 20000, "채식(페스코)", "없음", "파스타", "아늑한", True),
                ("최민재", "인턴", "서울역", 25000, "없음", "없음", "아시안", "룸 좌석", False)]},
    {"id": "dev", "name": "개발팀", "title": "개발팀 스프린트 종료 회식", "lead": "정우진 리드", "size": 12, "area": "마포·용산",
     "visits": [("hist-d1", "합정 고깃간", 4.2, True, 32000, "2026-09-26"),
                ("hist-d2", "연남 타코", 3.6, False, 21000, "2026-08-29"),
                ("hist-d3", "공덕 족발집", 4.4, True, 26000, "2026-07-31"),
                ("hist-d4", "망원 피자", 2.8, False, 24000, "2026-06-26")],
     "people": [("정우진", "리드", "판교", 35000, "없음", "없음", "고기", "술 한잔", True),
                ("한소희", "개발자", "강남", 30000, "없음", "없음", "일식", "활기찬", True),
                ("오세훈", "개발자", "성수", 30000, "비건", "없음", "아시안", "조용한 분위기", True)]},
    {"id": "sales", "name": "영업팀", "title": "영업팀 분기 마감 회식", "lead": "배준호 팀장", "size": 9, "area": "마포·용산",
     "visits": [("hist-s1", "마포 한정식 다온", 4.7, True, 35000, "2026-09-30"),
                ("hist-s2", "용산 스테이크 하우스", 3.9, False, 45000, "2026-06-30"),
                ("hist-s3", "공덕 수육 명가", 4.3, True, 28000, "2026-03-31"),
                ("hist-s4", "이태원 훠궈", 2.5, False, 30000, "2025-12-30")],
     "people": [("배준호", "팀장", "서울역", 40000, "없음", "없음", "한식", "룸 좌석", True),
                ("윤가은", "과장", "광화문", 30000, "없음", "조개", "한식", "조용한 분위기", True)]},
]

if __name__ == "__main__":
    st = Store()
    for d in DEPTS:
        st.db.execute("INSERT OR REPLACE INTO groups(id, name) VALUES (?, ?)", (d["id"], d["name"]))
        st.db.execute("DELETE FROM participants WHERE meeting_id IN (SELECT id FROM meetings WHERE group_id=?)", (d["id"],))
        st.db.execute("DELETE FROM meetings WHERE group_id=?", (d["id"],))
        st.db.commit()
        st.clear_group(d["id"])
        for pid, name, sat, rev, pp, day in d["visits"]:
            st.add_visit(Feedback(group_id=d["id"], place_id=pid, place_name=name, attrs=[], satisfaction=sat,
                                  revisit=rev, per_person=pp), visited_at=day)
        m = st.add_meeting(d["id"], d["title"], WHEN, d["area"], d["lead"], d["size"])
        for n, role, origin, budget, diet, allergy, food, mood, done in d["people"]:
            p = st.add_participant(m["id"], n, role, origin=origin, budget=budget, diet=diet, allergy=allergy, food=food, mood=mood)
            st.set_done(p["token"], done)
    print("seeded:", [g["name"] for g in st.groups()])
