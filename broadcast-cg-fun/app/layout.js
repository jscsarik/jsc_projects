export const metadata = {
  title: '실시간 방송 오버레이 시스템',
  description: 'Supabase Realtime 기반 방송 전광판 & 리모컨 시스템',
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body className="bg-black text-white antialiased m-0 p-0">
        {children}
      </body>
    </html>
  );
}
