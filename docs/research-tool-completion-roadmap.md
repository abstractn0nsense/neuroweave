# NeuroWeave Research Tool Completion Roadmap

작성일: 2026-05-25

업데이트: 2026-05-26, `main` 기준 코드 재검토 및 worker CLI preprocessing/epoching/ERP subpipeline 머지 반영

## 현재 판단

현재 NeuroWeave는 "실제 데이터로 끝까지 도는 분석 MVP"에서 "research exploration alpha 기반"으로 한 단계 올라왔다. UI hydration/CORS 안정화와 preprocessing/epoching/ERP worker CLI 분리는 완료되어 `main`에 머지되었다. processing pipeline의 실행 경계는 이제 API process 내부 multiprocessing target이 아니라 worker CLI subprocess로 통일되었다.

6월 10일까지의 현실적인 목표는 여전히 "논문 결과 산출용 완성판"이 아니라, 실제 공개 EEG 데이터를 반복해서 넣고 검토할 수 있는 내부 연구 탐색용 alpha이다.

## 진행 수준 요약

| 항목 | 현재 수준 | 근거 | 다음 판단 |
| --- | --- | --- | --- |
| UI hydration + CORS | 완료 | `loadDatasetContext(datasetId)` 도입, CORS env/localhost port 옵션 반영, PR #5 머지 | 유지보수만 |
| preprocessing worker CLI | 완료 | `eeg_processing.worker_cli preprocessing`, API subprocess 전환, worker artifact 저장, PR #6 머지 | 유지보수만 |
| Phase 2/3 browser smoke | 완료 | `npm run e2e:all` 추가, Phase 2 + Phase 3 epoch + ERP smoke 통과 | CI/릴리스 검증에 계속 사용 |
| epoching/ERP worker CLI | 완료 | `eeg_processing.worker_cli epoching/erp`, API subprocess 전환, worker artifact/exit code 저장, PR #8 머지 | 유지보수만 |
| BIDS sidecar ingest MVP | 미완료 | `packages/eeg-io/src/eeg_io/bids_sidecars.py` 없음 | 다음 subpipeline 1순위 |
| Event mapping v2 | 미완료 | null 처리/row filter/condition preset 모델 없음 | BIDS sidecar ingest와 같이 설계 |
| structured warning/diagnostics | 미완료 | 기존 `warnings: list[str]` 중심 | BIDS ingest 후 warning inventory 기반으로 추가 |
| QC dashboard MVP | 미완료 | artifact는 있으나 단계별 QC UI/JSON은 아직 제한적 | 6월 초 MVP |
| Export bundle MVP | 미완료 | artifact manifest는 있으나 report bundle 없음 | QC 후 진행 |

## 현재 코드 검증 결과

검증 기준 시점: 2026-05-26, `main` 커밋 `afe0df9 Run epoching and ERP through worker CLI`

- Git 상태: clean, `main...origin/main`
- Python 테스트:
  - 명령: `apps/api/.venv/Scripts/python.exe -m pytest tests --basetemp=data/cache/pytest-tmp -o cache_dir=data/cache/pytest-cache`
  - 결과: 126 passed
  - 주의: Windows 기본 temp 권한 문제를 피하기 위해 repo 내부 `--basetemp`를 표준 테스트 명령으로 사용한다.
- Web build:
  - 명령: `C:\Program Files\nodejs\npm.cmd run build`
  - 결과: TypeScript check 및 Vite build 통과
  - 주의: PowerShell에서 `npm.ps1`이 execution policy에 막힐 수 있으므로 `npm.cmd`를 직접 호출한다.
- Browser smoke:
  - 명령: `C:\Program Files\nodejs\npm.cmd run e2e:all`
  - 결과: Phase 2 preprocessing, Phase 3 epoch, Phase 3 ERP smoke 통과

## 완료된 안정화

### 1. UI hydration + CORS

완료 범위:

- `apps/web/src/main.tsx`에 `loadDatasetContext(datasetId)` 도입
- active dataset 변경/새로고침 후 dataset detail, event log, validation, preprocessing/epoch/ERP runs 동시 hydration
- `/events`, `/validation`의 정상 404는 빈 상태로 처리
- `NEUROWEAVE_CORS_ORIGINS` env 기반 allowlist 추가
- `NEUROWEAVE_CORS_ALLOW_LOCALHOST_PORTS=true`로 임시 localhost/127.0.0.1 포트 허용 가능

완료 기준 충족:

- mapped event log가 새로고침 후 `Unmapped`로 돌아가지 않음
- dev server port가 바뀌어도 설정 기반으로 API 연결 가능
- Python/API CORS 테스트와 web build 통과

### 2. preprocessing worker CLI

완료 범위:

- `packages/eeg-processing/src/eeg_processing/worker_cli.py`
- 실행 형태: `python -m eeg_processing.worker_cli preprocessing --payload payload.json --result result.json`
- payload/result JSON schema v1 고정
- API preprocessing 실행을 worker CLI subprocess로 전환
- Windows subprocess 호환을 위해 API가 `PYTHONPATH`를 명시적으로 전달
- worker payload/result/stdout/stderr artifact 저장
- `output_metadata`에 worker artifact path, schema version, exit code 기록
- worker failure에서도 exit code와 artifact 보존

완료 기준 충족:

- preprocessing run이 API 내부 multiprocessing target 직접 호출 없이 실행됨
- Windows spawn/pickle/result queue 의존 제거
- 기존 API response shape 유지
- Python 테스트, web build, browser smoke 통과

## 6월 10일까지의 현실 목표

6월 10일까지 완료 가능한 범위는 초반 안정화 전체와 중반 일부이다.

완료 목표:

- UI hydration + CORS env화: 완료
- preprocessing worker CLI 분리: 완료
- epoching/ERP worker CLI 분리: 완료
- BIDS sidecar ingest MVP
- BIDS event mapping/filter preset MVP
- structured warning/diagnostics MVP
- QC dashboard 1차
- export bundle MVP
- 공개 EEG 데이터 최소 2종에서 ingest -> preprocessing -> epoch -> ERP -> comparison 통합 smoke

6월 10일 이후로 미루는 범위:

- full statistics phase
- permutation test 및 multiple comparison correction
- full reproducibility graph
- collaboration/share snapshot
- 대규모 visual regression suite
- multi-subject batch의 완성형 UI

### 3. epoching/ERP worker CLI

완료 범위:

- `worker_cli.py`에 `epoching`, `erp` job routing 추가
- epoching payload/result JSON schema v1 정의
- ERP payload/result JSON schema v1 정의
- API epoching 실행을 worker CLI subprocess로 전환
- API ERP 실행을 worker CLI subprocess로 전환
- preprocessing/epoching/ERP 공통 subprocess helper 정리
- worker payload/result/stdout/stderr artifact 저장
- worker exit code와 schema version을 run metadata에 기록
- result JSON 누락, invalid JSON, non-object JSON 실패 테스트 추가

완료 기준 충족:

- preprocessing -> epoch -> ERP 전체가 CLI worker 경유로 실행됨
- cancellation warning 문구와 기존 API response shape 유지
- ERP preview artifact endpoint와 comparison summary 흐름 유지
- Python 전체 테스트, web build, browser smoke, GitHub CI 통과

## 완료된 subpipeline: epoching/ERP worker CLI 확장

목표: preprocessing에서 검증된 worker CLI 계약을 epoching/ERP에도 확장해, 전체 processing pipeline의 실행 경계를 API process 밖으로 통일한다.

상태: 완료, PR #8 머지.

### 작업 0. Baseline 및 브랜치

- `main` 최신 상태 확인
- 새 브랜치 생성: `codex/worker-cli-epoch-erp`
- 전체 Python 테스트, web build, `npm run e2e:all` baseline 실행
- 아직 코드 수정 없음

완료 기준:

- branch clean
- Python tests 126 passed
- web build 통과
- browser smoke 통과

### 작업 1. worker CLI job routing 확장

- `worker_cli.py`에 `epoching`, `erp` job command 추가
- 기존 preprocessing schema는 유지
- epoching/ERP payload/result v1 초안 추가
- job mismatch, schema mismatch, payload validation 실패 처리 공통화

완료 기준:

- `python -m eeg_processing.worker_cli epoching --help`
- `python -m eeg_processing.worker_cli erp --help`
- 기존 preprocessing CLI 테스트 통과

### 작업 2. epoching CLI 실행 추가

- `run_epoching_job`의 Queue 결과 shape를 CLI result JSON으로 이식
- event log/config payload를 JSON 직렬화 가능한 형태로 정의
- API response shape는 변경하지 않음
- worker artifact 저장 경로는 preprocessing과 같은 패턴 사용

완료 기준:

- epoching CLI success/failure 단위 테스트 통과
- API epoch run이 CLI subprocess 경유로 completed/failed 처리
- cancellation warning 문구 유지

### 작업 3. ERP CLI 실행 추가

- `run_erp_job`의 Queue 결과 shape를 CLI result JSON으로 이식
- ERP config, comparison prep과 충돌 없이 artifact root 유지
- plot warning/failure를 기존 warning 흐름과 호환

완료 기준:

- ERP CLI success/failure 단위 테스트 통과
- API ERP run이 CLI subprocess 경유로 completed/failed 처리
- ERP preview artifact endpoint 유지

### 작업 4. 공통 worker subprocess wrapper 정리

- preprocessing/epoching/ERP의 payload write, subprocess launch, result read, stdout/stderr 저장 로직 중복 최소화
- job별 validation과 metadata만 분리
- 과한 abstraction은 피하고 API 호출부 가독성 유지

완료 기준:

- 세 job 모두 worker artifact path와 exit code 기록
- result JSON 누락/invalid JSON/non-object result 실패 테스트 통과
- 기존 run JSON backward compatibility 유지

### 작업 5. 통합 회귀 및 browser smoke

- `tests/test_api_preprocessing.py`
- `tests/test_api_epoch_execution.py`
- `tests/test_api_epoch_runs.py`
- `tests/test_api_erp_runs.py`
- `tests/test_worker_cli.py`
- 전체 Python tests
- web build
- `npm run e2e:all`

완료 기준:

- preprocessing -> epoch -> ERP 전체가 CLI worker 경유
- Python tests 통과
- browser smoke 통과
- PR mergeable

## 이번 주 남은 계획: 5월 27일-5월 31일

### 5월 27일 수요일

- BIDS sidecar ingest 설계 및 모듈 추가
- `_channels.tsv`, `_eeg.json` 파서 추가
- `RecordingMetadata` optional 확장 지점 확정

완료 기준:

- sidecar 파일이 없어도 기존 ingest 흐름이 깨지지 않음
- `_channels.tsv`의 channel type/status/units 후보를 구조화해서 읽을 수 있음

### 5월 28일 목요일

- `_eeg.json` metadata 반영
- line frequency, reference, sampling metadata 저장
- OpenNeuro `.set` 계열 warning을 structured warning 후보로 분류

완료 기준:

- sidecar metadata가 registry optional field로 보존됨
- 기존 JSON registry와 API response backward compatibility 유지

### 5월 29일 금요일

- BIDS events normalization 시작
- `n/a`, `NA`, empty null 처리
- row filter 모델 초안
- `bids_events` preset 초안

완료 기준:

- BIDS `events.tsv`를 기존 EventLog 모델로 안정적으로 변환
- condition derivation 입력이 UI/API에서 일관되게 보임

### 5월 30일 토요일

- Event mapping v2 확장
- `psychopy`, `eeglab_annotations` preset 초안
- raw row/source column 일부 보존
- mapping preview와 validation 메시지 갱신

완료 기준:

- null/filter/preset 처리가 API와 UI에서 같은 결과를 낸다
- 기존 event upload/mapping API 테스트가 유지된다

### 5월 31일 일요일

- structured diagnostics 모델 초안
- 기존 string warning과 병행
- 실제 공개 데이터 2종 통합 smoke
- 6월 1일 이후 backlog 재조정

완료 기준:

- warning 원인/영향/조치가 최소 구조로 저장됨
- 6월 1일 QC/export 착수 여부 판단 가능

## 6월 1일-6월 10일 큰 흐름

- 6월 1일-3일: ResearchDataset/provenance 계층 정리, source manifest/checksum 최소 구현
- 6월 4일-5일: QC dashboard MVP
- 6월 6일-7일: export bundle MVP, artifact manifest schema 정리
- 6월 8일: validation suite smoke 고정
- 6월 9일: 버그 수정, UX 정리, docs 업데이트
- 6월 10일: release candidate tag, demo dataset 기준 최종 검증

## 초반 안정화: 구조 안정화 중심

목표: 지금 MVP를 "실제 공개 데이터 여러 개를 반복해서 안전하게 처리하는 기반"으로 바꾼다.

### 1. `ResearchDataset` 계층 추가

기존 `Dataset`, `Recording`, `EventLog`, `Run`은 유지하되 source/provenance 계층을 분리한다.

- `SourceDataset`: source name, URL, DOI, license, downloaded file manifest
- `BidsSidecarSet`: eeg_json, channels_tsv, electrodes_tsv, coordsystem_json, events_tsv
- `RecordingMetadata`: 기존 channel names 외에 channel types, bads, line frequency, reference, units 추가
- 기존 JSON registry는 깨지지 않게 optional field로 확장

### 2. BIDS sidecar ingest

새 모듈 권장:

- `packages/eeg-io/src/eeg_io/bids_sidecars.py`
- `read_bids_sidecars(base_path)`
- `apply_channel_sidecar(raw, channels_tsv)`
- `normalize_bids_events(events_tsv, preset)`

처리 목표:

- `_channels.tsv`의 `type`, `status`, `units` 반영
- `_eeg.json`의 `PowerLineFrequency`, `EEGReference`, sampling metadata 저장
- OpenNeuro `.set` warning을 "자동 보정됨/metadata 부족"으로 구조화

### 3. Event mapping v2

현재 mapping은 column mapping 중심이다. 연구용은 filtering과 condition derivation이 필요하다.

- `row_filter`: `trial_type == stimulus`
- `condition_column`: `value`, `trial_type`, `stim_file` 등
- `null_values`: `["n/a", "NA", ""]`
- preset: `psychopy`, `bids_events`, `eeglab_annotations`
- normalized event에는 `raw_row`, `source_file`, `source_columns` 일부 보존

### 4. Structured warning model

기존 `warnings: list[str]`는 유지하되, 새 `diagnostics.warnings[]`를 추가한다.

- `code`: `mne_unknown_channel_types`
- `severity`: `info | warning | risk | error`
- `source`: `mne | bids | validation | worker`
- `impact`
- `suggested_action`

UI는 raw warning 대신 이 구조를 우선 표시한다.

## 중반: 연구 워크플로우 확장

목표: 단일 파일 데모를 넘어서 "분석 검토가 가능한 워크벤치"로 만든다.

- QC dashboard
  - preprocessing: channel type, reference, filter, resampling, bad channels, annotations
  - epoch: condition counts, dropped epochs, out-of-bounds events, baseline summary
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

초반과의 호환성 유의점:

- `output_metadata`는 compact summary만 유지하고, 큰 QC는 별도 JSON artifact로 저장
- legacy `raw_preprocessed.fif`, `epochs.fif`, `evoked_*.fif` fallback은 최소 한두 phase 유지
- API response shape는 optional field 추가 방식으로만 확장

## 후반: 연구급 완성

목표: "결과를 논문/프로젝트 분석에 쓸 수 있다"고 말할 수 있는 수준으로 올린다.

- 통계 Phase
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
4. BIDS sidecar ingest
5. BIDS event mapping/filter preset
6. structured warning/diagnostics
7. QC dashboard MVP
8. export bundle MVP
9. batch/multi-subject foundation
10. statistics/reproducibility/collaboration

## 결론

현재는 "research exploration alpha 기반"이 확보된 상태다. worker CLI 경계는 preprocessing/epoching/ERP까지 통일되었으므로, 다음 단계는 실제 공개 EEG 데이터 호환성을 높이는 BIDS sidecar ingest와 Event mapping v2이다. 이 작업이 끝나야 structured diagnostics, QC, export를 안정적으로 얹을 수 있다.

6월 10일까지는 research exploration alpha를 목표로 한다. 즉, 실제 공개 EEG 데이터를 안정적으로 반복 처리하고, mapping/validation/run 상태가 새로고침 후에도 일관되며, worker 실행 경계가 CLI로 분리되어 이후 BIDS ingest, QC, export, 재현성 기능을 얹을 수 있는 기반을 만드는 것이 핵심이다.
