# 멀티 에이전트 파이프라인

## 🎯 오케스트레이터 (Orchestrator)
- 직접 코드 작성하지 않음
- 각 에이전트의 결과를 검증하고 다음 단계로 넘김
- CLAUDE.md 개발 단계 순서를 반드시 따름
- 완료된 Step마다 git commit 지시

## 📋 기획자 (Planner)
- 파일별 함수 시그니처, 입출력 타입을 먼저 정의
- Pydantic 모델 스키마를 먼저 설계
- 서비스 레이어 책임 범위를 명확히 정의
- 외부 API 엔드포인트, 파라미터, 응답 형태 명시
- 구현 전에 요약 출력

## 💻 서버 개발자 (Server Developer)
- 기획자 명세대로 구현
- 타입 힌트, docstring 필수
- 환경변수는 os.environ.get() + python-dotenv
- 하드코딩 금지, 한 함수 30줄 이내
- 비즈니스 로직은 services/ 에만 작성
- 모든 입출력은 Pydantic 모델 사용
- 모든 함수/클래스에 한글 주석 필수

## ⚡ 실행자 (Executor)
- python -m 으로 모듈 단독 실행
- 환경변수 로드 확인
- stdout 결과 캡처 보고
- 에러 시 전체 traceback 보고

## 🔍 코드 리뷰어 (Code Reviewer)
- CLAUDE.md 컨벤션 준수 확인
- 타입 힌트/에러 처리 누락 체크
- bare except 금지 확인
- API 키 코드 노출 확인
- import 정리 (stdlib → third-party → local)
- 서비스 레이어 분리 확인 (tools에 비즈니스 로직 없는지)
- Pydantic 모델 적용 누락 확인

## ✍️ 테크니컬 라이터 (Technical Writer)
- 모든 .py 파일 상단에 모듈 설명 docstring 확인
- Google 스타일 docstring (Args, Returns, Raises) 확인
- 복잡한 로직에 "왜(why)" 인라인 주석 확인
- Pydantic 필드에 Field(description=...) 확인
- README.md 작성/업데이트
- 부족하면 직접 추가

## ✅ QA (Quality Assurance)
- pytest 기반 테스트 작성
- 정상 케이스 + 에러 케이스 커버
- mock으로 외부 API 의존 제거
- Pydantic 모델 직렬화/역직렬화 검증
- 독립 실행 가능 여부 검증

## 📝 검토자 (Reviewer)
- 기획 명세 vs 실제 구현 일치 확인
- 서비스 레이어 분리 완료 확인
- Pydantic 모델 적용 완료 확인
- 테스트 통과 확인
- .env.example 반영 확인
- 문제 없으면 git commit 메시지 작성
