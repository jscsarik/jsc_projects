class AudioManager {
  private ctx: AudioContext | null = null;
  private intervalId: any = null;
  // Store active nodes to stop them immediately
  private nodes: any[] = [];

  private initCtx() {
    if (!this.ctx) {
      this.ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    if (this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  /**
   * Plays the dialing tone (Korean/US style: 440Hz + 480Hz dual tone, 1 sec on, 2 sec off).
   */
  playDialing() {
    this.initCtx();
    this.stopAll();
    if (!this.ctx) return;

    const playTone = () => {
      if (!this.ctx) return;

      const osc1 = this.ctx.createOscillator();
      const osc2 = this.ctx.createOscillator();
      const gainNode = this.ctx.createGain();

      osc1.frequency.value = 440;
      osc2.frequency.value = 480;
      osc1.type = 'sine';
      osc2.type = 'sine';

      gainNode.gain.setValueAtTime(0, this.ctx.currentTime);
      gainNode.gain.linearRampToValueAtTime(0.08, this.ctx.currentTime + 0.05);
      gainNode.gain.setValueAtTime(0.08, this.ctx.currentTime + 1.0);
      gainNode.gain.linearRampToValueAtTime(0, this.ctx.currentTime + 1.05);

      osc1.connect(gainNode);
      osc2.connect(gainNode);
      gainNode.connect(this.ctx.destination);

      osc1.start();
      osc2.start();

      osc1.stop(this.ctx.currentTime + 1.1);
      osc2.stop(this.ctx.currentTime + 1.1);

      const nodeRef = { osc1, osc2, gainNode };
      this.nodes.push(nodeRef);

      // Clean up reference after it ends
      setTimeout(() => {
        this.nodes = this.nodes.filter((n) => n !== nodeRef);
      }, 1500);
    };

    playTone();
    // Repeat every 3 seconds (1s tone + 2s silence)
    this.intervalId = setInterval(playTone, 3000);
  }

  /**
   * Plays a repeating classic/electronic ringtone for incoming calls.
   */
  playIncoming() {
    this.initCtx();
    this.stopAll();
    if (!this.ctx) return;

    const playTone = () => {
      if (!this.ctx) return;

      const now = this.ctx.currentTime;
      // Ascending sequence: E5, G5, C6
      const notes = [659.25, 783.99, 1046.50];
      const duration = 0.15;
      const oscillators: OscillatorNode[] = [];
      const gainNodes: GainNode[] = [];

      notes.forEach((freq, idx) => {
        if (!this.ctx) return;
        const osc = this.ctx.createOscillator();
        const gainNode = this.ctx.createGain();

        osc.frequency.value = freq;
        osc.type = 'triangle';

        const startTime = now + idx * 0.15;
        gainNode.gain.setValueAtTime(0, startTime);
        gainNode.gain.linearRampToValueAtTime(0.08, startTime + 0.02);
        gainNode.gain.setValueAtTime(0.08, startTime + duration - 0.02);
        gainNode.gain.linearRampToValueAtTime(0, startTime + duration);

        osc.connect(gainNode);
        gainNode.connect(this.ctx.destination);

        osc.start(startTime);
        osc.stop(startTime + duration + 0.05);

        oscillators.push(osc);
        gainNodes.push(gainNode);
      });

      const nodeRef = { oscillators, gainNodes };
      this.nodes.push(nodeRef);

      setTimeout(() => {
        this.nodes = this.nodes.filter((n) => n !== nodeRef);
      }, 1000);
    };

    playTone();
    // Repeat every 1.5 seconds
    this.intervalId = setInterval(playTone, 1500);
  }

  /**
   * Plays a pleasant ascending chime when call is connected.
   */
  playSuccess() {
    this.initCtx();
    this.stopAll();
    if (!this.ctx) return;

    const now = this.ctx.currentTime;
    const notes = [523.25, 659.25, 783.99, 1046.50]; // C5, E5, G5, C6
    notes.forEach((freq, idx) => {
      if (!this.ctx) return;
      const osc = this.ctx.createOscillator();
      const gainNode = this.ctx.createGain();

      osc.frequency.value = freq;
      osc.type = 'sine';

      const startTime = now + idx * 0.08;
      gainNode.gain.setValueAtTime(0, startTime);
      gainNode.gain.linearRampToValueAtTime(0.06, startTime + 0.02);
      gainNode.gain.setValueAtTime(0.06, startTime + 0.18);
      gainNode.gain.linearRampToValueAtTime(0, startTime + 0.22);

      osc.connect(gainNode);
      gainNode.connect(this.ctx.destination);

      osc.start(startTime);
      osc.stop(startTime + 0.25);
    });
  }

  /**
   * Plays a descending sequence when call ends.
   */
  playEnd() {
    this.initCtx();
    this.stopAll();
    if (!this.ctx) return;

    const now = this.ctx.currentTime;
    const notes = [392.00, 329.63, 261.63]; // G4, E4, C4
    notes.forEach((freq, idx) => {
      if (!this.ctx) return;
      const osc = this.ctx.createOscillator();
      const gainNode = this.ctx.createGain();

      osc.frequency.value = freq;
      osc.type = 'sine';

      const startTime = now + idx * 0.1;
      gainNode.gain.setValueAtTime(0, startTime);
      gainNode.gain.linearRampToValueAtTime(0.06, startTime + 0.02);
      gainNode.gain.setValueAtTime(0.06, startTime + 0.12);
      gainNode.gain.linearRampToValueAtTime(0, startTime + 0.15);

      osc.connect(gainNode);
      gainNode.connect(this.ctx.destination);

      osc.start(startTime);
      osc.stop(startTime + 0.2);
    });
  }

  /**
   * Silences all synthesized tones and clears interval timers immediately.
   */
  stopAll() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }

    // Immediately stop and disconnect all active oscillators
    this.nodes.forEach((nodeRef) => {
      try {
        if (nodeRef.osc1) {
          nodeRef.osc1.stop();
          nodeRef.osc1.disconnect();
          nodeRef.osc2.stop();
          nodeRef.osc2.disconnect();
          nodeRef.gainNode.disconnect();
        }
        if (nodeRef.oscillators) {
          nodeRef.oscillators.forEach((osc: OscillatorNode) => {
            try { osc.stop(); } catch {}
            try { osc.disconnect(); } catch {}
          });
          nodeRef.gainNodes.forEach((gain: GainNode) => {
            try { gain.disconnect(); } catch {}
          });
        }
      } catch {
        // Ignore errors for already stopped nodes
      }
    });

    this.nodes = [];
  }
}

export const audioManager = new AudioManager();
