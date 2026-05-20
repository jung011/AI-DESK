"""Kaflix A2A 사이드카 연동 모듈 — backend 의 `external/` 패키지와 짝.

역할 분담:
  backend `external/`  →  사내 *공유* control-plane (172.20.1.1:8080) 직접 호출
                          (사내 동료 AI 목록 등)
  helper  `kaflix/`    →  본인 mac 의 *개인* 사이드카 (127.0.0.1:9876) 직접 호출
                          (본인 employeeId 자동 감지, inbox SSE 구독 등)

여기 모인 코드들의 공통점은 *케플릭스 사이드카/control-plane spec 변경에 직접 의존* 한다는 것.
spec 변경 시 fix 가 필요한 지점들이 한 폴더에 모여있어 추적이 쉬워진다.

서브모듈:
  - identity: 사이드카 /.well-known/agent.json 으로 본인 employeeId 자동 감지
  - inbox_pump: 사이드카 /channel/events SSE 구독 → (me) liki tmux 자동 푸시
"""

from .identity import DEFAULT_SIDECAR_URL, detect_local_employee_id
from .inbox_pump import pump_loop

__all__ = ["DEFAULT_SIDECAR_URL", "detect_local_employee_id", "pump_loop"]
