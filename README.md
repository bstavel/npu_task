# NPU-Threat Test (Pygame)

A Pygame implementation of the NPU-threat test for assessing fear and anxiety in humans, based on:

> Schmitz, A. & Grillon, C. (2012). Assessing fear and anxiety in humans using the threat of predictable and unpredictable aversive events (the NPU-threat test). *Nature Protocols*, 7(3), 527–532.

## Overview

The NPU-threat test presents three conditions:

- **N (Neutral)** — No shock. A green circle may appear but signals nothing.
- **P (Predictable)** — Shock only during the red square cue (0.5 s before cue offset).
- **U (Unpredictable)** — Shock at any time, but never during the blue triangle cue.

Startle probes (white noise bursts) are delivered during cue and inter-trial interval (ITI) periods to measure the blink reflex via EMG.

## Task Structure

1. **Pre-test habituation** — 9 startle probes
2. **Block 1** — 4 habituation probes, then 7 conditions (e.g., P N U N U N P)
3. **Break** — experimenter checks in with participant
4. **Block 2** — 4 habituation probes, then 7 conditions (opposite order)

Each condition lasts ~120–135 s and contains 3 cue presentations (8 s each) with 6 startle probes (3 during cue, 3 during ITI). Startle probes are separated by a minimum of 20 s. Each block delivers 6 shocks total (1–2 per P/U condition).

Block order is counterbalanced across participants (order 1: P N U N U N P, order 2: U N P N P N U).

## Setup

### Requirements

```
pip install -r requirements.txt
```

Dependencies: `pygame`, `pyserial` (required when using serial TTL output).

### Stimuli

The task expects stimulus files in `stimuli/`:

- `GreenCircle.png` — N condition cue
- `RedSquare.png` — P condition cue
- `BlueTriangle.png` — U condition cue
- `npustim.wav` — startle probe sound (103 dB white noise, 40 ms)

If this directory does not exist, unzip `NPU_orginal.zip` and rename it to `stimuli`.

## Running the Task

```
python npu_task.py
```

The startup screen collects:

1. **Participant ID** — typed, press ENTER to confirm
2. **Block order** — press 1 or 2
3. **Serial port** — auto-detected list, press number to select (or 0 to skip)

Data is saved to `npu_data/sub-{pid}_npu_{timestamp}.csv`.

## Serial TTL Output

The task sends TTL codes over a serial port to a splitter (DUB-26 / BNC):

| Event         | Code | Destination              |
|---------------|------|--------------------------|
| Startle probe | 4    | SAGA (EMG marker)        |
| Shock marker  | 2    | SAGA (shock event marker) |
| Shock trigger | 8    | Stimulator (delivers shock) |

On shock events, code 2 and code 8 are sent sequentially with a buffer flush between them.

Set `USE_SERIAL = False` in `npu_task.py` to run without serial hardware.

### Testing Triggers

```
python test_triggers.py
```

Walks through each trigger type interactively so you can verify SAGA and stimulator reception before running the full task.

## Output

Each run produces a CSV in `npu_data/` with columns:

| Column | Description |
|--------|-------------|
| `participant_id` | Subject identifier |
| `block` | Block number (0 = habituation, 1, 2) |
| `condition` | N, P, U, or HAB |
| `event_type` | e.g., `startle_probe`, `cue_onset`, `shock`, `condition_start` |
| `cue_shape` | Stimulus filename when a cue is active |
| `context` | CUE or ITI |
| `cue_number` | Which of the 3 cues within a condition (0–2) |
| `abs_time` | Unix timestamp |
| `exp_time` | Seconds since experiment start |
| `condition_time` | Seconds since current condition start |

## Configuration

Key constants at the top of `npu_task.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `FULLSCREEN` | `True` | Fullscreen or windowed mode |
| `CUE_DURATION` | `8.0` | Cue display time (seconds) |
| `MIN_PROBE_INTERVAL` | `20.0` | Minimum gap between startle probes |
| `SHOCKS_PER_BLOCK` | `6` | Total shocks per block |
| `USE_SERIAL` | `True` | Enable/disable serial TTL output |
| `SERIAL_BAUD` | `9600` | Serial port baud rate |

## Reference

- Protocol paper: `2012_Schmitz_Nat. Protoc-_...Grillon.pdf`
- Supplementary timing table: `StuppTable1.pdf`
