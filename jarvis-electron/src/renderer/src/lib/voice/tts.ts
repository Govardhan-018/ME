/** Text-to-speech via the browser SpeechSynthesis API (offline, zero deps). */

export function speak(text: string, onEnd?: () => void): void {
  const synth = typeof window !== 'undefined' ? window.speechSynthesis : undefined
  if (!synth || !text) {
    onEnd?.()
    return
  }
  synth.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.rate = 1.03
  u.pitch = 1

  const voices = synth.getVoices()
  const preferred =
    voices.find((v) => /^en/i.test(v.lang) && /(david|guy|daniel|aria|jenny|male)/i.test(v.name)) ||
    voices.find((v) => /^en/i.test(v.lang))
  if (preferred) u.voice = preferred

  u.onend = () => onEnd?.()
  u.onerror = () => onEnd?.()
  synth.speak(u)
}

export function stopSpeaking(): void {
  if (typeof window !== 'undefined') window.speechSynthesis?.cancel()
}
