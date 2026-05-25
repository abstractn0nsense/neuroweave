# NeuroWeave 사용자 가이드

이 문서는 현재 로컬 NeuroWeave 앱으로 EEG 데이터셋을 만들고,
전처리, epoch, ERP preview, comparison prep까지 실행하는 방법을 설명합니다.

## 1. 실행하기

Windows에서 저장소 루트의 `Start NeuroWeave.bat`를 실행합니다.

앱 주소:

```text
http://127.0.0.1:5173
```

API 주소:

```text
http://127.0.0.1:8000
```

서버를 끄려면 `Stop NeuroWeave.bat`를 실행합니다.

## 2. 화면 구조

현재 UI는 두 화면으로 나뉩니다.

### Setup

연구 컨텍스트와 데이터셋을 정하는 화면입니다.

- `Study Setup`: project와 experiment를 생성하거나 선택합니다.
- `Dataset Queue`: participant/session 단위의 dataset을 생성하거나 선택합니다.
- `Active Dataset`: 현재 선택된 dataset의 준비 상태를 보여줍니다.
- `Sample Metadata`: 저장소 샘플 EEG 파일의 metadata를 확인합니다.

Dataset Queue에서 dataset을 선택해도 자동으로 분석 화면으로 넘어가지 않습니다.
준비 상태를 확인한 뒤 `Continue Analysis`를 눌러야 Analysis 화면으로 이동합니다.

### Analysis

실제 파일 업로드와 분석을 실행하는 화면입니다.

- `Active Dataset`: 현재 분석 대상 dataset과 준비 상태입니다.
- `Ingestion And Preprocessing`: EEG 파일, event log, event mapping, validation, preprocessing을 처리합니다.
- `Epoch Controls`: 완료된 preprocessing run에서 epoch를 생성합니다.
- `ERP Preview`: 완료된 epoch run에서 ERP artifact와 plot을 생성합니다.
- `QC Dashboard`: manifest 기반 artifact와 warning 요약을 보여줍니다.

## 3. 빠른 테스트용 파일

이미 로컬에 테스트 가능한 파일이 있습니다.

공개 PhysioNet 예제:

```text
EEG Recording:
C:\neuroweave\data\raw\public-samples\S001R03.edf

Event Log:
C:\neuroweave\data\raw\public-samples\S001R03_events.csv
```

작은 fixture 예제:

```text
EEG Recording:
C:\neuroweave\tests\fixtures\eeg\sample_resting_raw.fif

Event Log:
C:\neuroweave\tests\fixtures\events\psychopy_minimal.csv
```

PhysioNet 예제는 실제 공개 EDF 파일이고, fixture 예제는 빠른 테스트용입니다.

## 4. Dataset 만들기

1. `Setup` 탭으로 갑니다.
2. `Study Setup`에서 project 이름을 입력하고 `Create Project`를 누릅니다.
3. experiment 이름을 입력하고 `Create Experiment`를 누릅니다.
4. `Dataset Queue`에서 participant와 session을 입력하고 `Create Dataset`을 누릅니다.
5. `Active Dataset`에 dataset 상태가 표시되는지 확인합니다.
6. `Continue Analysis`를 눌러 Analysis 화면으로 이동합니다.

Dataset은 보통 한 명의 participant와 한 session을 의미합니다.

## 5. EEG Recording 업로드

Analysis 화면의 `Ingestion And Preprocessing`에서 `EEG Recording`에 원본 EEG 파일을 넣습니다.

현재 지원 형식:

- FIF
- EDF
- BDF
- BrainVision VHDR
- EEGLAB SET

파일을 선택한 뒤 `Upload EEG`를 누릅니다. 성공하면 dataset 상태가 file을 가진 상태로 바뀌고, backend가 sampling rate, duration, channel count, channel names 등을 읽습니다.

## 6. Event Log 업로드

`Event Log`에는 실험 이벤트 CSV 또는 TSV를 넣습니다.

Event log는 자극이나 trial이 언제 발생했는지 알려주는 표입니다. 최소한 onset time이 필요합니다.

예시:

```csv
onset,duration,trial_type,stimulus
4.200000,4.100000,T2,right_fist
12.500000,4.100000,T1,left_fist
```

업로드 후 `Event Mapping`에서 어떤 컬럼이 어떤 의미인지 지정합니다.

중요한 mapping:

- `onset_seconds`: 이벤트 시작 시간입니다. 필수입니다.
- `duration_seconds`: 이벤트 지속 시간입니다.
- `trial_type`: condition label로 가장 자주 쓰입니다.
- `stimulus`: 자극 이름입니다.
- `response`, `correct`, `reaction_time_seconds`: 행동 데이터가 있을 때 사용합니다.

Mapping을 확인한 뒤 `Save Mapping`을 누릅니다.

## 7. Dataset Validation

`Validate Dataset`을 누르면 NeuroWeave가 다음을 확인합니다.

- EEG recording이 있는지
- event log가 mapping되었는지
- event onset이 recording duration 안에 있는지
- 필수 metadata가 빠지지 않았는지

성공하면 `Dataset is valid.`가 표시되고 preprocessing을 시작할 수 있습니다.

## 8. Preprocessing 실행

기본 설정:

- high-pass: `1`
- low-pass: `40`
- reference: `average`

선택 설정:

- notch filter
- resample rate
- custom reference

`Start Preprocessing`을 누르면 run이 queue에 들어갑니다. 완료되면 run row가 `completed`로 바뀌고, processed FIF와 diagnostics가 저장됩니다.

주의:

- low-pass, high-pass는 입력 sampling rate의 Nyquist frequency보다 낮아야 합니다.
- resample rate는 입력 sampling rate보다 높게 설정할 수 없습니다.
- custom reference는 실제 존재하는 channel 이름이어야 합니다.

## 9. Epoch 생성

`Epoch Controls`에서 완료된 preprocessing run을 선택합니다.

주요 설정:

- `condition_field`: condition으로 사용할 event field입니다. 보통 `trial_type`을 씁니다.
- `tmin_seconds`: 이벤트 기준 epoch 시작 시간입니다.
- `tmax_seconds`: 이벤트 기준 epoch 종료 시간입니다.
- baseline: baseline correction 범위입니다.
- reject EEG: threshold 기반 epoch rejection 값입니다.

`Start Epoch`을 누르면 epoch artifact가 생성됩니다. 완료되면 condition count, epoch count, dropped epoch count가 표시됩니다.

## 10. ERP Preview 생성

`ERP Preview`에서 완료된 epoch run을 선택합니다.

기본 mode는 GFP plot입니다. 특정 channel을 보고 싶으면 channel plot mode를 선택하고 channel 이름을 입력합니다.

`Generate ERP`를 누르면 condition별 evoked FIF, PNG, SVG, metadata가 생성됩니다. 성공하면 preview plot이 화면에 표시됩니다.

## 11. Comparison Prep

완료된 ERP run에 condition이 2개 이상 있으면 comparison prep을 실행할 수 있습니다.

설정:

- condition A
- condition B
- GFP 또는 channel target
- mean-amplitude time window

현재 comparison은 descriptive summary입니다. 통계 검정은 이후 단계에서 추가될 예정입니다.

## 12. Export와 재현성

완료된 run은 다음 정보를 남깁니다.

- input file checksum과 metadata
- config snapshot
- output artifact path
- diagnostics JSON
- artifact manifest
- warnings와 errors
- MNE/Python version 정보

이 정보는 같은 분석을 반복하거나, 왜 결과가 달라졌는지 비교하기 위한 핵심 근거입니다.

## 13. 문제 해결

업로드 버튼이 비활성화되어 있으면:

- 파일을 선택했는지 확인합니다.
- active dataset이 선택되어 있는지 확인합니다.

preprocessing 버튼이 비활성화되어 있으면:

- EEG와 event log가 모두 업로드되었는지 확인합니다.
- event mapping을 저장했는지 확인합니다.
- `Validate Dataset`이 성공했는지 확인합니다.

epoch 또는 ERP가 비활성화되어 있으면:

- 완료된 preprocessing run이 있는지 확인합니다.
- 완료된 epoch run이 있는지 확인합니다.

화면이 예상과 다르면:

- `Refresh`를 누릅니다.
- 필요하면 `Setup`에서 active dataset을 다시 선택합니다.
- 서버가 이상하면 `Stop NeuroWeave.bat` 후 `Start NeuroWeave.bat`를 다시 실행합니다.

## 14. 현재 한계

- 통계 검정은 아직 구현 전입니다.
- ICA와 advanced artifact correction은 향후 단계입니다.
- 협업, 계정, cloud storage는 아직 local prototype 이후 단계입니다.
- 현재는 연구 워크플로우 검증과 재현 가능한 artifact 생성에 초점을 둡니다.
## 15. PhysioNet EEGMMI 공개 데모

실제 공개 EEG 데이터로 NeuroWeave를 시험하려면 저장소 루트에서 다음을
실행합니다.

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\prepare_physionet_eegmmi_demo.py
```

이 스크립트는 PhysioNet EEG Motor Movement/Imagery Dataset의 `S001R03.edf`를
`data/raw/public-samples/` 아래에 다운로드하고, EDF+ annotation을 읽어
`S001R03_events.csv`를 만듭니다. `data/` 폴더는 git에서 제외되어 있으므로
공개 EDF와 생성된 CSV는 커밋하지 않습니다.

업로드할 파일:

```text
EEG Recording:
C:\neuroweave\data\raw\public-samples\S001R03.edf

Event Log:
C:\neuroweave\data\raw\public-samples\S001R03_events.csv
```

Event Mapping에서는 다음처럼 지정합니다.

- `onset_seconds` -> `onset`
- `duration_seconds` -> `duration`
- `trial_type` -> `trial_type`
- `stimulus` -> `stimulus`

이후 `Validate Dataset`, preprocessing, epoch, ERP preview 순서로 진행합니다.
자세한 영어 문서는 `docs/public-demo-physionet-eegmmi.md`를 참고합니다.
