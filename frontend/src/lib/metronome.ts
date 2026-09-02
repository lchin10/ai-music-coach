/**
 * A metronome that doesn't drift.
 *
 * `setInterval` is audibly wrong within about a minute — the JS timer is not
 * a clock, and on a tempo-building drill a metronome that lies is worse than
 * no metronome at all. So this is the standard lookahead scheduler: a coarse
 * ~25 ms timer that queues oscillators against `audioContext.currentTime`
 * roughly 100 ms ahead, where the audio hardware keeps time, not the browser.
 */

const LOOKAHEAD_MS = 25;
const SCHEDULE_AHEAD = 0.1; // seconds

export class Metronome {
  private ctx: AudioContext | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private nextNoteTime = 0;
  private beat = 0;

  bpm = 60;
  beatsPerBar = 4;

  /** Fires on each scheduled beat so the UI can flash in time. */
  onBeat: ((beat: number) => void) | null = null;

  get running() {
    return this.timer !== null;
  }

  private click(time: number, accent: boolean) {
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.frequency.value = accent ? 1600 : 1000;
    // A short exponential fade — a hard stop clicks and gets tiring fast.
    gain.gain.setValueAtTime(accent ? 0.5 : 0.3, time);
    gain.gain.exponentialRampToValueAtTime(0.001, time + 0.05);
    osc.connect(gain).connect(this.ctx.destination);
    osc.start(time);
    osc.stop(time + 0.06);
  }

  private tick = () => {
    if (!this.ctx) return;
    while (this.nextNoteTime < this.ctx.currentTime + SCHEDULE_AHEAD) {
      this.click(this.nextNoteTime, this.beat === 0);
      const current = this.beat;
      const delay = (this.nextNoteTime - this.ctx.currentTime) * 1000;
      if (this.onBeat) setTimeout(() => this.onBeat?.(current), Math.max(0, delay));
      this.nextNoteTime += 60 / this.bpm;
      this.beat = (this.beat + 1) % Math.max(1, this.beatsPerBar);
    }
  };

  start() {
    if (this.running) return;
    // Constructed on the click, not on page load — browsers refuse to start
    // an AudioContext without a gesture.
    this.ctx ??= new AudioContext();
    void this.ctx.resume();
    this.beat = 0;
    this.nextNoteTime = this.ctx.currentTime + 0.05;
    this.timer = setInterval(this.tick, LOOKAHEAD_MS);
  }

  stop() {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  dispose() {
    this.stop();
    void this.ctx?.close();
    this.ctx = null;
  }
}
