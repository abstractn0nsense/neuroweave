# NeuroWeave Research Tool Completion Roadmap

작성일: 2026-05-25

업데이트: 2026-05-30, Phase C exit gate 및 Phase D entry plan 반영

## 현재 판단

NeuroWeave는 현재 "실제 데이터로 끝까지 도는 분석 MVP"를 넘어
"research exploration alpha" 기반에 도달했다. 실행 경계는
preprocessing, epoching, ERP 모두 worker CLI subprocess로 통일되었고,
workflow template, batch execution, retry/cancel, QC summary, analysis report,
export bundle까지 단일 run과 batch-created run 양쪽에서 검증되어 있다.

Phase D는 새 대형 기능을 벌리는 단계가 아니라, 이미 들어간
BIDS/event/QC/export/batch MVP를 실제 공개 EEG 데이터 기준으로 단단하게
닫는 단계다. 기준 문서는 `docs/phase-d-entry-plan.md`이다.

6월 10일까지의 현실적인 목표는 여전히 "논문 결과 산출용 완성판"이
아니다. 목표는 PhysioNet EEGMMI와 OpenNeuro/BIDS 계열 공개 데이터에서
ingest -> preprocessing -> epoch -> ERP -> comparison 흐름을 반복 검증할
수 있는 내부 연구 탐색용 alpha이다.

## 진행 수준 요약

| 항목 | 현재 수준 | 근거 | 다음 판단 |
| --- | --- | --- | --- |
| UI hydration + CORS | 완료 | `loadDatasetContext(datasetId)` 도입, CORS env/localhost port 옵션 반영 | 유지보수만 |
| preprocessing worker CLI | 완료 | `eeg_processing.worker_cli preprocessing`, API subprocess 전환, worker artifact 저장 | 유지보수만 |
| epoching/ERP worker CLI | 완료 | `eeg_processing.worker_cli epoching/erp`, API subprocess 전환, worker artifact/exit code 저장 | 유지보수만 |
| Phase 2/3/C browser smoke | 완료 | `npm run e2e:all`이 Phase 2, Phase C batch, Phase 3 epoch, Phase 3 ERP smoke 실행 | CI/릴리스 검증에 계속 사용 |
| Workflow templates | 완료 | template persistence, apply preview, subject-specific field exclusion, review-required handling 테스트 보유 | Phase D에서는 호환성 유지 |
| Batch execution | 완료 | persisted batch plan, worker execution, retry, cancellation, partial completion, summary artifact 구현 | Phase D에서는 public data smoke와 export 호환성 유지 |
| BIDS sidecar parsing | MVP 있음 | `packages/eeg-io/src/eeg_io/bids_sidecars.py`, `_channels.tsv`, `_eeg.json` parser 테스트 | Phase D에서 discovery/upload 연동으로 hardening |
| Event mapping v2 | MVP 있음 | preset, row filter, provenance snapshot API/UI 경로와 테스트 존재 | Phase D에서 BIDS `events.tsv` normalization hardening |
| Structured warning/diagnostics | MVP 있음 | run diagnostics에 structured warning 병행, UI는 structured warning 우선 표시 | Phase D에서 taxonomy 안정화 |
| QC dashboard/summary | MVP 있음 | preprocessing/epoch/ERP QC summary와 UI dashboard 경로 존재 | Phase D에서 sidecar/provenance/diagnostics 표시 보강 |
| Export bundle | MVP 있음 | report, manifest, diagnostics, figures, provenance, artifacts, batch context 포함 | Phase D에서 public data metadata 포함 보강 |

## 현재 코드 검증 결과

검증 기준 시점: 2026-05-30, Phase C exit gate 이후 current-regression check

- Git 상태:
  - 명령: `git status --short --branch`
  - 결과: `## main...origin/main`
- Python 테스트:
  - 명령: `.\apps\api\.venv\Scripts\python.exe -m pytest --basetemp=data\cache\pytest`
  - 결과: 250 passed
  - 주의: Windows 기본 temp/cache 권한 문제를 피하기 위해 repo 내부
    `--basetemp`를 표준 테스트 명령으로 사용한다.
- Web build:
  - 명령: `npm.cmd run build`
  - 작업 경로: `apps/web`
  - 결과: TypeScript check 및 Vite build 통과
  - 주의: PowerShell에서 `npm.ps1`이 execution policy에 막힐 수 있으므로
    `npm.cmd`를 직접 호출한다.
- Browser smoke:
  - 명령: `npm.cmd run e2e:all`
  - 작업 경로: `apps/web`
  - 결과: Phase 2 preprocessing, Phase C batch retry, Phase 3 epoch,
    Phase 3 ERP smoke 통과

## 완료된 안정화

### 1. UI Hydration + CORS

완료 범위:

- `apps/web/src/main.tsx`에 `loadDatasetContext(datasetId)` 도입
- active dataset 변경/새로고침 후 dataset detail, event log, validation,
  preprocessing/epoch/ERP runs 동시 hydration
- `/events`, `/validation`의 정상 404는 빈 상태로 처리
- `NEUROWEAVE_CORS_ORIGINS` env 기반 allowlist 추가
- `NEUROWEAVE_CORS_ALLOW_LOCALHOST_PORTS=true`로 임시 localhost/127.0.0.1
  포트 허용 가능

완료 기준 충족:

- mapped event log가 새로고침 후 `Unmapped`로 돌아가지 않음
- dev server port가 바뀌어도 설정 기반으로 API 연결 가능
- Python/API CORS 테스트와 web build 통과

### 2. Worker CLI Execution Boundary

완료 범위:

- `packages/eeg-processing/src/eeg_processing/worker_cli.py`
- preprocessing, epoching, ERP job routing
- payload/result JSON schema v1 유지
- API processing 실행을 worker CLI subprocess로 전환
- Windows subprocess 호환을 위해 API가 `PYTHONPATH`를 명시적으로 전달
- worker payload/result/stdout/stderr artifact 저장
- worker exit code와 schema version을 run metadata에 기록
- result JSON 누락, invalid JSON, non-object JSON 실패 테스트 보유

완료 기준 충족:

- preprocessing -> epoch -> ERP 전체가 API 내부 multiprocessing target 직접
  호출 없이 실행됨
- Windows spawn/pickle/result queue 의존 제거
- 기존 API response shape 유지
- Python 테스트, web build, browser smoke 통과

### 3. Workflow Templates And Batch Execution

완료 범위:

- workflow template persistence와 apply preview
- source run id 같은 application-time binding 제외
- subject-specific field exclusion
- review-required/stale preview batch item 실행 차단
- persisted batch plan과 immutable template snapshot
- local batch worker execution
- failed item retry
- pending/running batch cancellation
- partial completion
- `batch_summary.json` artifact
- QC summary, analysis report, export bundle의 batch context

완료 기준 충족:

- Phase C browser smoke가 multi-dataset batch와 failed subject retry를 검증
- batch-created runs도 일반 run의 artifact integrity, QC summary,
  analysis report, export bundle contract를 유지
- cancellation은 terminal cancelled state와 summary artifact를 남김

## Phase D: Public Data Hardening

기준 문서: `docs/phase-d-entry-plan.md`

Phase D 목표:

- BIDS sidecar discovery를 upload/registration 흐름에 연결
- source/provenance manifest와 checksum 최소 구현
- BIDS `events.tsv` normalization hardening
- structured diagnostic warning taxonomy 안정화
- QC dashboard와 export bundle에 sidecar/provenance/diagnostics 반영
- PhysioNet EEGMMI와 OpenNeuro/BIDS 계열 공개 데이터 smoke 고정

Phase D에서 추가한 범위:

- 오래된 roadmap 상태 갱신
- public-dataset validation matrix
- sidecar discovery contract
- dataset metadata/provenance attachment
- event normalization source row/source column 보존
- BIDS, event mapping, validation, worker, artifact, export, batch warning
  taxonomy
- user guide와 release checklist 업데이트

Phase D 제외 범위:

- full statistics phase
- permutation test 및 multiple comparison correction
- full reproducibility graph와 one-click rerun
- collaboration/share snapshot
- 대규모 visual regression suite
- multi-subject batch의 완성형 UI

## Phase D 작업 단위

### D0. Baseline And Roadmap Sync

문서 정리 단계다. 런타임 코드는 건드리지 않는다.

- `docs/research-tool-completion-roadmap.md`를 현재 코드 상태에 맞게 갱신
- Phase C exit 상태 반영
- `docs/phase-d-entry-plan.md` 링크/참조 추가
- BIDS parser, event preset, structured warnings, QC summary, export bundle이
  "완전 미구현"이 아니라 "MVP 있음, Phase D에서 hardening" 상태임을 명확히 표시

완료 기준:

- 문서가 현재 코드와 충돌하지 않음
- Phase D scope와 exclusions가 명시됨

### D1. BIDS Sidecar Discovery Contract

- EEG/event 파일 근처에서 sidecar 후보 탐색
- `_eeg.json`, `_channels.tsv`, `_events.tsv` 감지
- optional future sidecar 자리 확보
- sidecar가 없어도 기존 upload 흐름은 그대로 동작
- invalid sidecar는 dataset을 망가뜨리지 않고 diagnostics로 기록

완료 기준:

- 기존 non-BIDS upload 회귀 없음
- sidecar fixture로 discovery/parser 테스트 통과
- invalid sidecar가 structured diagnostic warning/error로 남음

### D2. Dataset Metadata And Provenance Attachment

- optional metadata 필드로 sidecar 정보 저장
- EEG 파일, event 파일, sidecar 파일의 role, original filename, path, size,
  checksum 기록
- 기존 JSON registry record backward compatibility 유지
- API response에는 additive field로만 노출

완료 기준:

- 오래된 registry JSON도 로드됨
- 새 dataset API response에 provenance/sidecar metadata가 추가됨
- checksum/source manifest 테스트 추가

### D3. BIDS Events Normalization Hardening

- `n/a`, `NA`, empty string 등 null 처리 일관화
- row filter 결과와 원본 row count/filter count 보존
- `source_row`, selected source columns 보존
- condition derivation 지원
- 기존 PsychoPy/custom mapping 유지

완료 기준:

- BIDS events fixture가 EventLog로 안정 변환됨
- API preview와 UI preview 결과 일치
- 기존 event upload/mapping 테스트 유지

### D4. Diagnostic Warning Taxonomy

- 공통 warning schema 확정:
  - `code`
  - `severity`
  - `source`
  - `impact`
  - `suggested_action`
- source 범주 정리:
  - `bids`
  - `event_mapping`
  - `validation`
  - `worker`
  - `artifact`
  - `export_bundle`
  - `batch`
- legacy `warnings: list[str]` 유지
- UI는 structured diagnostics 우선 표시

완료 기준:

- 새 warning path는 structured diagnostics로 남음
- 기존 warning 테스트 통과
- UI warning card가 code/source/severity/impact/action을 안정 표시

### D5. Public Dataset Smoke Fixtures

- PhysioNet EEGMMI smoke workflow 정리
- OpenNeuro/BIDS-style sample workflow 추가 또는 문서화
- public EEG data는 `data/` 아래 ignored path에만 저장
- expected warnings snapshot 또는 문서화
- ingest -> preprocessing -> epoch -> ERP -> comparison 재현 절차 고정

완료 기준:

- maintainer가 명령만 따라 두 public dataset smoke를 재현 가능
- public data는 git에 커밋되지 않음
- warning이 예상/검토 항목으로 기록됨

### D6. QC And Export Review Polish

- QC dashboard에 sidecar/provenance/diagnostics 표시
- export bundle에 Phase D provenance/sidecar metadata 포함
- batch-created run의 batch context 유지
- missing optional metadata는 hard failure가 아니라 structured warning 처리

완료 기준:

- completed ERP run ZIP에 report, manifest, diagnostics, provenance, figures,
  artifacts 포함
- batch-created run도 QC/report/export에서 batch context 유지
- bundle structure는 기존과 호환

### D7. Phase D Exit Gate

- Python full test
- web build
- browser smoke `npm.cmd run e2e:all`
- 두 public dataset smoke 결과 기록
- user guide/release checklist 업데이트
- 남은 작업을 Phase E 이후로 명시 이관

완료 기준:

- regression gate 통과
- public dataset smoke 결과가 날짜/명령/결과와 함께 기록됨
- Phase E 범위가 분리됨

## 6월 10일까지의 현실 목표

완료 목표:

- Phase C template/batch foundation 유지
- BIDS sidecar discovery와 metadata/provenance 연결
- BIDS event mapping/filter preset hardening
- structured warning/diagnostics taxonomy
- QC dashboard 1차 polish
- export bundle provenance/diagnostics polish
- 공개 EEG 데이터 최소 2종에서 ingest -> preprocessing -> epoch -> ERP ->
  comparison 통합 smoke

6월 10일 이후로 미루는 범위:

- full statistics phase
- permutation test 및 multiple comparison correction
- full reproducibility graph
- collaboration/share snapshot
- 대규모 visual regression suite
- multi-subject batch의 완성형 UI

## 중반: 연구 워크플로우 확장

목표: 단일 파일 데모를 넘어서 "분석 검토가 가능한 워크벤치"로 만든다.

- QC dashboard
  - preprocessing: channel type, reference, filter, resampling, bad channels,
    annotations
  - epoch: condition counts, dropped epochs, out-of-bounds events, baseline
    summary
  - ERP: nave, GFP peak, selected channel peak, plot status
- Batch/multi-run support
  - subject/session/run grouping
  - 여러 preprocessing/epoch/ERP run을 batch로 생성
  - failed run retry
- Analysis config versioning
  - config hash
  - parent run id chain
  - artifact manifest schema version
- ERP comparison 확장
  - channel/ROI 선택
  - time window 저장
  - mean amplitude, peak amplitude, latency
  - per-condition metric table
- Export bundle
  - `analysis_report.json`
  - figures
  - artifact manifest
  - source/provenance
  - config snapshots

호환성 유의점:

- `output_metadata`는 compact summary만 유지하고, 큰 QC는 별도 JSON artifact로 저장
- legacy `raw_preprocessed.fif`, `epochs.fif`, `evoked_*.fif` fallback은 최소
  한두 phase 유지
- API response shape는 optional field 추가 방식으로만 확장

## 후반: 연구급 완성

목표: "결과를 논문/프로젝트 분석에 쓸 수 있다"고 말할 수 있는 수준으로 올린다.

- 통계 phase
  - subject-level table
  - paired/unpaired test
  - permutation test option
  - multiple comparison correction
  - effect size, confidence interval
- Reproducibility
  - full run graph
  - source file checksum
  - package versions
  - OS/Python/MNE version
  - one-click rerun
- Validation suite
  - PhysioNet, OpenNeuro `.set`, EDF/BDF/BrainVision 샘플 고정 smoke
  - expected warning snapshot
  - visual regression for ERP preview
- Data governance
  - local-only mode
  - PHI/subject label warning
  - delete/export project
- Collaboration
  - project archive
  - shareable report
  - immutable completed analysis snapshot

## 추천 순서

1. UI hydration + CORS env화: 완료
2. preprocessing worker CLI 분리: 완료
3. epoching/ERP worker CLI 확장: 완료
4. workflow template + batch foundation: 완료
5. D0 roadmap sync: 완료
6. D1 BIDS sidecar discovery contract
7. D2 dataset metadata/provenance attachment
8. D3 BIDS events normalization hardening
9. D4 diagnostic warning taxonomy
10. D5 public dataset smoke fixtures
11. D6 QC/export review polish
12. D7 Phase D exit gate
13. statistics/reproducibility/collaboration

## 결론

현재는 Phase C foundation이 닫힌 상태이며 Phase D를 시작할 수 있다. worker
CLI 경계, template, batch, QC summary, analysis report, export bundle은 이미
기본 계약을 갖췄다. 다음 핵심은 실제 공개 EEG 데이터 호환성을 높이는
BIDS sidecar discovery, event normalization, provenance, structured diagnostics
hardening이다.

Phase D는 이 기반을 public dataset smoke로 검증 가능한 형태까지 끌어올리는
단계다. 통계 검정, full reproducibility graph, collaboration snapshot은 Phase D
이후로 분리한다.
