# StarcraftCoach

스타크래프트 리마스터 **4:4 빅헌터** 리플레이를 자동 분석하는 개인 코치 (패키지명 `bhcoach`).
게임이 끝나면 리플레이를 읽어 빌드 타임라인·상대 성향·처방을 HTML 리포트로 보여준다.

- 리플레이 파일만 읽는다. 게임 클라이언트·메모리에는 일절 접근하지 않는다.
- 외부 Python 패키지 없음 (표준 라이브러리만 사용)

## 요구사항

- Windows 10/11, Python 3.10+
- `bin/screp.exe` — 리플레이 파서 [icza/screp](https://github.com/icza/screp) v1.13.8 (Apache-2.0, `bin/screp-LICENSE.txt`)
  - 저장소에는 포함하지 않는다. [릴리스](https://github.com/icza/screp/releases)에서 받거나 `go build ./cmd/screp`로 빌드해 `bin/`에 둔다.

## 사용법

```bat
python -m bhcoach init            :: config.json 생성 → my_name, replay_dir 확인
python -m bhcoach import          :: 기존 리플레이 일괄 가져오기 (하위 폴더 포함)
python -m bhcoach watch           :: 감시 모드 (run_watch.bat 더블클릭과 동일)
python -m bhcoach report          :: 가장 최근 경기 리포트
python -m bhcoach report --game 12
python -m bhcoach profile RAMBO-  :: 특정 플레이어 성향
python -m bhcoach list -n 30      :: 최근 경기 목록
```

`config.json` 주요 항목:

| 키 | 기본값 | 설명 |
|---|---|---|
| `my_name` | `KIMCHI2022` | 내 배틀넷 닉네임 |
| `replay_dir` | `문서\StarCraft\Maps\Replays` | 리플레이 폴더 |
| `map_keywords` | `["big hunters", "빅헌"]` | 맵 이름에 포함되면 빅헌터로 판정 |
| `min_games_for_compare` | `30` | 승/패 비교를 켜는 최소 판수 |

## 리포트 구성

1. **이번 판 처방** — 규칙 기반
   - 상대가 과거에 1분 이내 풀을 자주 했으면 포지/캐논 타이밍 경고
   - 상대 첫 뮤탈 중앙값 대비 우리 팀 첫 커세어 타이밍 점검
   - 상대 럴커 사용 이력 대비 옵저버 타이밍 점검
   - 내가 이긴 판 중앙값보다 60초 이상 늦은 빌드
   - 초반 탈락(명령 끊김) 감지
2. **참가자** — APM/EAPM, 마지막 명령 시각
3. **빌드 타임라인** — 종족별 주요 건물·유닛 첫 지시 시각, 분당 캐논/크립 수
4. **상대 프로필** — 이번 판 이전 기록의 중앙값 (사후 편향 방지)
5. **승/패 비교** — 같은 종족 플레이어(팀원 포함)를 승/패로 나눠 중앙값 비교 (30판 이상)

## 한계

- 리플레이는 **명령 기록**이다. 자원 부족으로 실패한 건설 지시도 포함될 수 있다.
- 유닛 수(뮤탈 몇 기 등)는 정확히 알 수 없어 '첫 등장 시각'만 사용한다.
- 승패는 screp 판정 기준이며, 판정 불가 경기는 비교에서 제외된다.

## 테스트

```bat
python -m unittest discover -s tests
```
