export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const text = searchParams.get('text') || '';

    if (!text.trim()) {
      return new Response('Text is required', { status: 400 });
    }

    // 최대 100자까지 안전하게 분할
    const cleanText = text.trim().slice(0, 100);
    const googleTtsUrl = `https://translate.google.com/translate_tts?ie=UTF-8&tl=ko&client=tw-ob&q=${encodeURIComponent(cleanText)}`;

    // Vercel 서버 사이드에서 구글 TTS 음성을 직접 받아옴 (CORS 및 브라우저 차단 우회)
    const response = await fetch(googleTtsUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        Referer: 'https://translate.google.com/',
      },
    });

    if (!response.ok) {
      return new Response('TTS fetch failed', { status: 500 });
    }

    const audioData = await response.arrayBuffer();

    return new Response(audioData, {
      headers: {
        'Content-Type': 'audio/mpeg',
        'Cache-Control': 'public, max-age=3600, stale-while-revalidate=86400',
      },
    });
  } catch (error) {
    console.error('[API TTS 에러]', error);
    return new Response('Internal Server Error', { status: 500 });
  }
}
