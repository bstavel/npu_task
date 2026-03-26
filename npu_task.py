#!/usr/bin/env python3
"""
NPU-Threat Test — Pygame Implementation
=========================================
Based on: Schmitz & Grillon (2012) Nature Protocols 7(3), 527-532.

Assessing fear and anxiety in humans using the threat of predictable
and unpredictable aversive events (the NPU-threat test).

This script implements the full NPU-threat test with:
  - Pre-test habituation (9 startle probes)
  - Two blocks of 7 conditions each (P N U N U N P  or  U N P N P N U)
  - Counterbalanced block order
  - Startle probes during cue and ITI periods
  - Shock event scheduling (placeholder — serial delivery added later)
  - Detailed CSV event log with millisecond-precision timestamps
"""

import pygame
import sys
import os
import csv
import time
import random
from datetime import datetime

# ════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════

FULLSCREEN = True
SCREEN_RES = (1920, 1080)       # fallback for windowed mode
BG_COLOR = (255, 255, 255)       # white
TEXT_COLOR = (0, 0, 0)           # black
MUTED_TEXT = (120, 120, 120)     # grey for footer text
HIGHLIGHT_COLOR = (0, 80, 180)   # dark blue for highlights
FPS = 60

# Timing constants (seconds) — based on Supplementary Table 1
CUE_DURATION = 8.0
MIN_PROBE_INTERVAL = 20.0
PROBE_CUE_OFFSETS = [4.5, 6.5]  # probe placed this far into an 8-s cue

PRE_HAB_COUNT = 9                # pre-test habituation probes
BLOCK_HAB_COUNT = 4              # per-block habituation probes
HAB_INTERVAL = (8, 13)           # inter-probe interval for habituation
HAB_FIRST_INTERVAL = (4, 7)     # first probe comes sooner

SHOCKS_PER_BLOCK = 6

CONDITION_ORDERS = {
    1: ["P", "N", "U", "N", "U", "N", "P"],
    2: ["U", "N", "P", "N", "P", "N", "U"],
}

CUE_FILES = {
    "N": "GreenCircle.png",
    "P": "RedSquare.png",
    "U": "BlueTriangle.png",
}

CONTEXT_TEXT = {
    "N": "No shock",
    "P": "Shock only during red square",
    "U": "Shock at any time",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STIMULI_DIR = os.path.join(SCRIPT_DIR, "NPU_orginal")
DATA_DIR = os.path.join(SCRIPT_DIR, "npu_data")
STARTLE_WAV = "npustim.wav"


# ════════════════════════════════════════════════════════════════
# SCHEDULE GENERATION
# ════════════════════════════════════════════════════════════════

def _make_event(t, etype, **kwargs):
    """Helper to build a schedule event dict."""
    evt = {"time": t, "type": etype}
    evt.update(kwargs)
    return evt


def generate_habituation_probes(start_time, count,
                                interval=HAB_INTERVAL,
                                first_interval=HAB_FIRST_INTERVAL):
    """Return (events_list, last_probe_time) for a habituation series."""
    events = []
    t = start_time + random.uniform(*first_interval)
    for i in range(count):
        events.append(_make_event(t, "startle_probe",
                                  condition="HAB", context="ITI",
                                  cue_shape="", cue_index=-1))
        if i < count - 1:
            t += random.uniform(*interval)
    return events, t


def allocate_shocks(condition_order):
    """Assign 1-2 shocks per P/U condition, totalling SHOCKS_PER_BLOCK.

    Returns dict mapping condition-index → shock count (only P/U entries).
    """
    threat_idx = [i for i, c in enumerate(condition_order) if c in ("P", "U")]
    n = len(threat_idx)
    # Brute-sample until the total is correct (converges fast)
    while True:
        counts = [random.choice([1, 2]) for _ in range(n)]
        if sum(counts) == SHOCKS_PER_BLOCK:
            break
    return {ti: c for ti, c in zip(threat_idx, counts)}


def _generate_condition_events(cond_type, cond_start, last_probe_time,
                               num_shocks, block_num):
    """Build the event list for one ~125-130 s condition.

    Returns (events, condition_end_time, last_probe_time_in_condition).
    """
    events = []
    cue_shape = CUE_FILES.get(cond_type, "")

    # ── context onset ────────────────────────────────────────
    events.append(_make_event(cond_start, "context_onset",
                              condition=cond_type, context="ITI",
                              cue_shape="", cue_index=-1))

    # ── choose pattern A or B ────────────────────────────────
    # Pattern A  (ITI probe first):  ITI CUE ITI CUE ITI CUE
    # Pattern B  (CUE first):        CUE ITI CUE ITI CUE ITI
    min_first = last_probe_time + MIN_PROBE_INTERVAL
    ideal_first_iti = cond_start + random.uniform(10, 16)
    actual_first_iti = max(ideal_first_iti, min_first + random.uniform(0, 2))
    use_a = (actual_first_iti - cond_start) <= 18

    probes = []          # (time, ctx, cue_idx)
    cues   = []          # (onset, offset, idx)

    # helpers ─────────────────────────────────────────────────
    def _add_cue_after_probe(prev_probe, ci):
        """Place a cue so the cue-probe is ≥ 20 s after prev_probe."""
        cpo = random.choice(PROBE_CUE_OFFSETS)
        min_gap = max(14.0, MIN_PROBE_INTERVAL - cpo)
        max_gap = min(18.0, 23.0 - cpo)
        if max_gap < min_gap:
            max_gap = min_gap + 1.0
        gap = random.uniform(min_gap, max_gap)
        onset = prev_probe + gap
        offset = onset + CUE_DURATION
        cue_probe = onset + cpo
        cues.append((onset, offset, ci))
        probes.append((cue_probe, "CUE", ci))
        return cue_probe, cpo, offset

    def _add_iti_after_cue(cue_probe_t, cue_offset_t, cpo):
        """Place an ITI probe ≥ 20 s after the preceding cue-probe."""
        remaining = CUE_DURATION - cpo
        lo = max(0.0, MIN_PROBE_INTERVAL - remaining)
        hi = max(lo + 1.0, 23.0 - remaining)
        gap_after = random.uniform(lo, hi)
        t = cue_offset_t + gap_after
        probes.append((t, "ITI", -1))
        return t

    # ── build the six probes + three cues ────────────────────
    if use_a:
        cur = actual_first_iti
        probes.append((cur, "ITI", -1))
        for ci in range(3):
            cur, cpo, c_off = _add_cue_after_probe(cur, ci)
            if ci < 2:
                cur = _add_iti_after_cue(cur, c_off, cpo)
    else:
        # first cue
        cpo = random.choice(PROBE_CUE_OFFSETS)
        onset = max(cond_start + random.uniform(7, 10),
                    min_first - cpo + random.uniform(0, 1))
        offset = onset + CUE_DURATION
        cue_probe = onset + cpo
        cues.append((onset, offset, 0))
        probes.append((cue_probe, "CUE", 0))
        cur = _add_iti_after_cue(cue_probe, offset, cpo)
        for ci in range(1, 3):
            cur, cpo, c_off = _add_cue_after_probe(cur, ci)
            cur = _add_iti_after_cue(cur, c_off, cpo)

    # ── condition end ────────────────────────────────────────
    last_cue_off = max(c[1] for c in cues)
    last_event = max(last_cue_off, probes[-1][0])
    cond_end = last_event + random.uniform(3, 7)

    # ── shock events ─────────────────────────────────────────
    shocks = []
    if cond_type == "P" and num_shocks > 0:
        eligible = list(range(3))
        random.shuffle(eligible)
        for ci in eligible[:num_shocks]:
            shocks.append((cues[ci][1] - 0.5, "CUE", ci))   # 0.5 s before offset
    elif cond_type == "U" and num_shocks > 0:
        # collect ITI windows (must not overlap cues)
        windows = []
        prev_end = cond_start
        for onset, offset, _ in sorted(cues, key=lambda c: c[0]):
            if onset - prev_end > 4:
                windows.append((prev_end + 1.5, onset - 1.0))
            prev_end = offset
        if cond_end - prev_end > 4:
            windows.append((prev_end + 1.5, cond_end - 1.0))
        random.shuffle(windows)
        for i in range(min(num_shocks, len(windows))):
            lo, hi = windows[i]
            shocks.append((random.uniform(lo, hi), "ITI", -1))

    # ── convert to event dicts ───────────────────────────────
    for onset, offset, ci in cues:
        events.append(_make_event(onset, "cue_onset",
                                  condition=cond_type, context="CUE",
                                  cue_shape=cue_shape, cue_index=ci))
        events.append(_make_event(offset, "cue_offset",
                                  condition=cond_type, context="CUE",
                                  cue_shape=cue_shape, cue_index=ci))
    for pt, ctx, ci in probes:
        events.append(_make_event(pt, "startle_probe",
                                  condition=cond_type, context=ctx,
                                  cue_shape=cue_shape if ctx == "CUE" else "",
                                  cue_index=ci))
    for st, ctx, ci in shocks:
        events.append(_make_event(st, "shock",
                                  condition=cond_type, context=ctx,
                                  cue_shape=cue_shape if ctx == "CUE" else "",
                                  cue_index=ci))
    events.append(_make_event(cond_end, "context_offset",
                              condition=cond_type, context="ITI",
                              cue_shape="", cue_index=-1))

    return events, cond_end, probes[-1][0]


def generate_block_schedule(block_num, condition_order):
    """Build the full event list for one block (4 hab probes + 7 conditions).

    All times are relative to block start (t = 0).
    Returns (events, block_duration).
    """
    events = []
    events.append(_make_event(0.0, "block_start",
                              condition="", context="", cue_shape="",
                              cue_index=-1))

    # 4 block-start habituation probes
    hab_evts, last_hab = generate_habituation_probes(0.0, BLOCK_HAB_COUNT)
    events.extend(hab_evts)

    # shock allocation
    shock_map = allocate_shocks(condition_order)

    # conditions
    cond_start = last_hab + random.uniform(8, 12)
    last_probe = last_hab

    for i, ctype in enumerate(condition_order):
        n_shocks = shock_map.get(i, 0)
        cond_evts, cond_end, cond_last_probe = _generate_condition_events(
            ctype, cond_start, last_probe, n_shocks, block_num
        )
        events.extend(cond_evts)
        last_probe = cond_last_probe
        if i < len(condition_order) - 1:
            cond_start = cond_end          # next condition starts immediately

    events.append(_make_event(cond_end, "block_end",
                              condition="", context="", cue_shape="",
                              cue_index=-1))
    return events, cond_end


def validate_schedule(events):
    """Verify that all startle probes are ≥ MIN_PROBE_INTERVAL apart
    (excluding habituation probes, which are intentionally closer).
    """
    probes = sorted(
        [e for e in events
         if e["type"] == "startle_probe" and e.get("condition") != "HAB"],
        key=lambda e: e["time"]
    )
    for i in range(1, len(probes)):
        gap = probes[i]["time"] - probes[i - 1]["time"]
        if gap < MIN_PROBE_INTERVAL - 0.5:      # 0.5 s tolerance for floats
            print(f"  WARNING: probe gap {gap:.2f}s at t={probes[i]['time']:.1f}")
    return True


# ════════════════════════════════════════════════════════════════
# CSV EVENT LOGGER
# ════════════════════════════════════════════════════════════════

class EventLogger:
    """Writes every experiment event to a CSV with precise timestamps."""

    COLUMNS = [
        "participant_id", "block", "condition", "event_type",
        "cue_shape", "context", "cue_number",
        "abs_time", "exp_time", "condition_time",
    ]

    def __init__(self, participant_id, filepath):
        self.participant_id = participant_id
        self.exp_start = None
        self._condition_start = None
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self._fh = open(filepath, "w", newline="")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(self.COLUMNS)

    def set_experiment_start(self, t):
        self.exp_start = t

    def set_condition_start(self, t):
        self._condition_start = t

    def log(self, event_type, block=0, condition="", cue_shape="",
            context="", cue_number=-1):
        now = time.time()
        exp_t = now - self.exp_start if self.exp_start else 0.0
        cond_t = now - self._condition_start if self._condition_start else 0.0
        self._writer.writerow([
            self.participant_id,
            block,
            condition,
            event_type,
            cue_shape,
            context,
            cue_number if cue_number >= 0 else "",
            f"{now:.4f}",
            f"{exp_t:.4f}",
            f"{cond_t:.4f}",
        ])
        self._fh.flush()

    def close(self):
        self._fh.close()


# ════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ════════════════════════════════════════════════════════════════

class Display:
    """All rendering logic lives here."""

    def __init__(self, screen):
        self.screen = screen
        self.W = screen.get_width()
        self.H = screen.get_height()
        # fonts
        self.font_title = pygame.font.Font(None, 72)
        self.font_body  = pygame.font.Font(None, 48)
        self.font_small = pygame.font.Font(None, 36)
        self.font_ctx   = pygame.font.Font(None, 60)
        # cue images (scaled to ~1/4 of screen height)
        cue_size = int(self.H * 0.28)
        self.cue_images = {}
        for cond, fname in CUE_FILES.items():
            path = os.path.join(STIMULI_DIR, fname)
            img = pygame.image.load(path).convert_alpha()
            img = pygame.transform.smoothscale(img, (cue_size, cue_size))
            self.cue_images[cond] = img

    # ── primitives ──────────────────────────────────────────
    def clear(self):
        self.screen.fill(BG_COLOR)

    def flip(self):
        pygame.display.flip()

    def _centered(self, surface, y):
        return surface.get_rect(center=(self.W // 2, y))

    def draw_text(self, text, y, font=None, color=TEXT_COLOR):
        font = font or self.font_body
        surf = font.render(text, True, color)
        self.screen.blit(surf, self._centered(surf, y))

    def draw_wrapped(self, text, y_start, font=None, color=TEXT_COLOR,
                     max_w=None):
        font = font or self.font_body
        max_w = max_w or int(self.W * 0.75)
        words = text.split()
        lines, cur = [], ""
        for w in words:
            test = f"{cur} {w}".strip()
            if font.size(test)[0] <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        y = y_start
        for line in lines:
            self.draw_text(line, y, font, color)
            y += font.get_linesize() + 6
        return y

    def draw_fixation(self):
        cx, cy = self.W // 2, self.H // 2
        s = 20
        pygame.draw.line(self.screen, TEXT_COLOR,
                         (cx - s, cy), (cx + s, cy), 3)
        pygame.draw.line(self.screen, TEXT_COLOR,
                         (cx, cy - s), (cx, cy + s), 3)

    def draw_context(self, condition):
        self.draw_text(CONTEXT_TEXT.get(condition, ""), y=90,
                       font=self.font_ctx)

    def draw_cue(self, condition):
        img = self.cue_images.get(condition)
        if img:
            self.screen.blit(img, self._centered(img, self.H // 2))

    # ── composite screens ───────────────────────────────────
    def instruction_screen(self, title, body, footer="Press SPACE to continue"):
        self.clear()
        self.draw_text(title, self.H // 4, self.font_title)
        self.draw_wrapped(body, self.H // 4 + 90, self.font_body)
        self.draw_text(footer, self.H - 70, self.font_small, MUTED_TEXT)
        self.flip()
        return self._wait_space()

    def break_screen(self):
        self.clear()
        self.draw_text("Break", self.H // 3, self.font_title)
        self.draw_text("Please inform the experimenter.",
                       self.H // 2, self.font_body)
        self.draw_text("Press SPACE when ready to continue.",
                       self.H * 2 // 3, self.font_small, MUTED_TEXT)
        self.flip()
        return self._wait_space()

    def end_screen(self):
        self.clear()
        self.draw_text("Experiment complete.", self.H // 3,
                       self.font_title)
        self.draw_text("Thank you for your participation.",
                       self.H // 2, self.font_body)
        self.draw_text("Press SPACE to exit.",
                       self.H * 2 // 3, self.font_small, MUTED_TEXT)
        self.flip()
        self._wait_space()

    def _wait_space(self):
        """Block until SPACE (return False) or ESC (return True)."""
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    return True
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_SPACE:
                        return False
                    if ev.key == pygame.K_ESCAPE:
                        return True
            pygame.time.wait(16)


# ════════════════════════════════════════════════════════════════
# STARTUP SCREEN
# ════════════════════════════════════════════════════════════════

def startup_screen(screen):
    """Collect participant ID and block-order selection.

    Returns (participant_id: str, block_order: int) or calls sys.exit().
    """
    W, H = screen.get_width(), screen.get_height()
    font_t = pygame.font.Font(None, 72)
    font_m = pygame.font.Font(None, 48)
    font_s = pygame.font.Font(None, 36)

    pid = ""
    order = None
    phase = "id"                  # 'id' → 'order'
    clock = pygame.time.Clock()

    while True:
        screen.fill(BG_COLOR)

        if phase == "id":
            _blit_center(screen, font_t, "NPU-Threat Test", H // 4)
            _blit_center(screen, font_m, "Enter Participant ID:", H // 2 - 40)
            _blit_center(screen, font_m, pid + "_", H // 2 + 30,
                         HIGHLIGHT_COLOR)
            _blit_center(screen, font_s, "Press ENTER when done",
                         H * 3 // 4, MUTED_TEXT)
        else:
            _blit_center(screen, font_t, f"Participant: {pid}", H // 5)
            _blit_center(screen, font_m, "Select Block 1 order:", H // 3)
            _blit_center(screen, font_m, "Press 1:  P N U N U N P",
                         H // 2 - 20, HIGHLIGHT_COLOR)
            _blit_center(screen, font_m, "Press 2:  U N P N P N U",
                         H // 2 + 40, HIGHLIGHT_COLOR)
            _blit_center(screen, font_s,
                         "(Block 2 will use the opposite order)",
                         H * 3 // 4, MUTED_TEXT)

        pygame.display.flip()

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if phase == "id":
                    if ev.key == pygame.K_RETURN and pid:
                        phase = "order"
                    elif ev.key == pygame.K_BACKSPACE:
                        pid = pid[:-1]
                    elif ev.unicode and (ev.unicode.isalnum()
                                         or ev.unicode in "_-"):
                        pid += ev.unicode
                else:
                    if ev.key in (pygame.K_1, pygame.K_KP1):
                        order = 1
                    elif ev.key in (pygame.K_2, pygame.K_KP2):
                        order = 2
                    if order is not None:
                        return pid, order

        clock.tick(FPS)


def _blit_center(screen, font, text, y, color=TEXT_COLOR):
    surf = font.render(text, True, color)
    screen.blit(surf, surf.get_rect(center=(screen.get_width() // 2, y)))


# ════════════════════════════════════════════════════════════════
# INSTRUCTION SCREENS
# ════════════════════════════════════════════════════════════════

def show_instructions(disp):
    """Walk the participant through the task instructions.

    Returns True if aborted (ESC), False otherwise.
    """
    screens = [
        ("NPU-Threat Test",
         "In this experiment, you will see different colored shapes on the "
         "screen. There are three different conditions, which will be "
         "explained on the following screens."),
        ("Condition 1: No Shock",
         "When you see 'No shock' at the top of the screen, you are "
         "completely safe. No shocks will be given during this condition. "
         "A green circle may occasionally appear, but it does not signal "
         "anything."),
        ("Condition 2: Predictable Shock",
         "When you see 'Shock only during red square' at the top of the "
         "screen, you may receive a mild shock — but ONLY when the red "
         "square is visible on screen. When the red square is not visible, "
         "you will not receive a shock."),
        ("Condition 3: Unpredictable Shock",
         "When you see 'Shock at any time' at the top of the screen, you "
         "may receive a mild shock at any moment, whether or not the blue "
         "triangle is visible on screen."),
        ("Important Information",
         "From time to time you will hear brief, loud sounds through the "
         "headphones. These are a normal part of the experiment. Please "
         "remain still and keep your eyes on the screen at all times. "
         "Try to avoid unnecessary movements."),
        ("Ready to Begin",
         "The experiment will now begin with a short habituation phase. "
         "Please focus on the cross in the center of the screen."),
    ]
    for title, body in screens:
        footer = ("Press SPACE to start" if title == "Ready to Begin"
                  else "Press SPACE to continue")
        if disp.instruction_screen(title, body, footer):
            return True
    return False


# ════════════════════════════════════════════════════════════════
# MAIN EXPERIMENT LOOP
# ════════════════════════════════════════════════════════════════

def run_phase(display, logger, events, startle_sound, block_num):
    """Execute a pre-generated schedule of events in real time.

    `events` have times relative to phase start (t = 0).
    Returns True if aborted (ESC), False otherwise.
    """
    timeline = sorted(events, key=lambda e: e["time"])
    if not timeline:
        return False

    # state
    condition   = None       # current condition letter or None
    cue_visible = False      # is a cue image on screen right now?
    idx         = 0
    clock       = pygame.time.Clock()
    phase_start = time.time()
    total_dur   = timeline[-1]["time"] + 2.0   # small buffer after last event

    while True:
        now     = time.time()
        elapsed = now - phase_start

        # exit when all events processed and buffer elapsed
        if elapsed >= total_dur and idx >= len(timeline):
            break

        # ── fire due events ──────────────────────────────────
        while idx < len(timeline) and timeline[idx]["time"] <= elapsed:
            evt   = timeline[idx]; idx += 1
            etype = evt["type"]

            if etype == "block_start":
                logger.log("block_start", block=block_num)

            elif etype == "block_end":
                logger.log("block_end", block=block_num)

            elif etype == "context_onset":
                condition = evt["condition"]
                cue_visible = False
                logger.set_condition_start(now)
                logger.log("condition_start", block=block_num,
                           condition=condition)

            elif etype == "context_offset":
                logger.log("condition_end", block=block_num,
                           condition=condition)
                condition = None
                cue_visible = False

            elif etype == "cue_onset":
                cue_visible = True
                logger.log("cue_onset", block=block_num,
                           condition=evt["condition"],
                           cue_shape=evt.get("cue_shape", ""),
                           context="CUE",
                           cue_number=evt.get("cue_index", -1))

            elif etype == "cue_offset":
                cue_visible = False
                logger.log("cue_offset", block=block_num,
                           condition=evt["condition"],
                           cue_shape=evt.get("cue_shape", ""),
                           context="CUE",
                           cue_number=evt.get("cue_index", -1))

            elif etype == "startle_probe":
                startle_sound.play()
                logger.log("startle_probe", block=block_num,
                           condition=evt.get("condition", "HAB"),
                           context=evt.get("context", "ITI"),
                           cue_shape=evt.get("cue_shape", ""),
                           cue_number=evt.get("cue_index", -1))

            elif etype == "shock":
                # TODO: send shock via serial port
                shock_elapsed = now - phase_start
                print(f"[SHOCK] t={shock_elapsed:.2f}s  "
                      f"condition={evt['condition']}  "
                      f"context={evt.get('context', '')}  "
                      f"cue_index={evt.get('cue_index', -1)}")
                logger.log("shock", block=block_num,
                           condition=evt["condition"],
                           context=evt.get("context", ""),
                           cue_shape=evt.get("cue_shape", ""),
                           cue_number=evt.get("cue_index", -1))

        # ── draw ─────────────────────────────────────────────
        display.clear()
        if condition:
            display.draw_context(condition)
            if cue_visible:
                display.draw_cue(condition)
            else:
                display.draw_fixation()
        else:
            display.draw_fixation()
        display.flip()

        # ── input ────────────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return True
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return True

        clock.tick(FPS)

    return False


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

def main():
    # ── initialise pygame ────────────────────────────────────
    pygame.init()
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

    if FULLSCREEN:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode(SCREEN_RES)
    pygame.display.set_caption("NPU-Threat Test")
    pygame.mouse.set_visible(False)

    # ── startup dialog ───────────────────────────────────────
    pid, block_order = startup_screen(screen)

    # ── prepare logging ──────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(DATA_DIR, f"sub-{pid}_npu_{ts}.csv")
    logger = EventLogger(pid, csv_path)

    # ── load assets ──────────────────────────────────────────
    disp = Display(screen)
    startle = pygame.mixer.Sound(os.path.join(STIMULI_DIR, STARTLE_WAV))

    # ── show instructions ────────────────────────────────────
    if show_instructions(disp):
        logger.close(); pygame.quit(); return

    # ── mark experiment start ────────────────────────────────
    exp_start = time.time()
    logger.set_experiment_start(exp_start)
    logger.log("experiment_start")

    # ── random seed (logged for reproducibility) ─────────────
    seed = int(exp_start * 1000) % (2**31)
    random.seed(seed)
    logger.log("random_seed", condition=str(seed))

    # ── generate schedules ───────────────────────────────────
    if block_order == 1:
        orders = [CONDITION_ORDERS[1], CONDITION_ORDERS[2]]
    else:
        orders = [CONDITION_ORDERS[2], CONDITION_ORDERS[1]]

    # pre-test habituation
    pre_hab_evts, _ = generate_habituation_probes(0.0, PRE_HAB_COUNT)

    # block 1 & 2
    b1_evts, _ = generate_block_schedule(1, orders[0])
    b2_evts, _ = generate_block_schedule(2, orders[1])

    # validate
    validate_schedule(b1_evts)
    validate_schedule(b2_evts)

    # ── run pre-test habituation ─────────────────────────────
    if run_phase(disp, logger, pre_hab_evts, startle, block_num=0):
        logger.log("experiment_abort")
        logger.close(); pygame.quit(); return

    # ── run block 1 ──────────────────────────────────────────
    if run_phase(disp, logger, b1_evts, startle, block_num=1):
        logger.log("experiment_abort")
        logger.close(); pygame.quit(); return

    # ── break ────────────────────────────────────────────────
    logger.log("break_start")
    if disp.break_screen():
        logger.log("experiment_abort")
        logger.close(); pygame.quit(); return
    logger.log("break_end")

    # ── run block 2 ──────────────────────────────────────────
    if run_phase(disp, logger, b2_evts, startle, block_num=2):
        logger.log("experiment_abort")
        logger.close(); pygame.quit(); return

    # ── done ─────────────────────────────────────────────────
    logger.log("experiment_end")
    disp.end_screen()
    logger.close()
    pygame.quit()


if __name__ == "__main__":
    main()
