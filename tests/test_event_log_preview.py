from eeg_io.event_logs import preview_event_log


def test_preview_event_log_reads_csv_headers_and_rows(tmp_path):
    path = tmp_path / "psychopy.csv"
    path.write_text(
        "stim_onset,condition,key_resp.keys,key_resp.rt\n"
        "1.0,target,space,0.42\n"
        "2.0,standard,,\n",
        encoding="utf-8",
    )

    preview = preview_event_log(path)

    assert preview["delimiter"] == ","
    assert preview["columns"] == [
        "stim_onset",
        "condition",
        "key_resp.keys",
        "key_resp.rt",
    ]
    assert preview["row_count"] == 2
    assert preview["preview_rows"][0]["condition"] == "target"


def test_preview_event_log_reads_tsv(tmp_path):
    path = tmp_path / "events.tsv"
    path.write_text(
        "onset\tduration\ttrial_type\n"
        "0.5\t0.2\tstim/left\n",
        encoding="utf-8",
    )

    preview = preview_event_log(path)

    assert preview["delimiter"] == "\t"
    assert preview["columns"] == ["onset", "duration", "trial_type"]
    assert preview["row_count"] == 1
