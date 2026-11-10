import { Link } from 'react-router-dom';
import { motion } from 'motion/react';

export default function Home() {
  return (
    <section className="relative h-[calc(100vh-5rem)] w-full flex items-center justify-center overflow-hidden bg-[#F5F2EB]">
      {/* Background Image */}
      <div className="absolute inset-0 z-0">
        <img
          src="/main-bg.jpg"
          alt="Main background"
          className="w-full h-full object-cover opacity-90 blur-[1px]"
          referrerPolicy="no-referrer"
        />
        <div className="absolute inset-0 bg-[#F5F2EB]/10 mix-blend-multiply" />
        <div className="absolute inset-0 bg-black/30" />
      </div>

      <div className="container mx-auto px-6 relative z-10 text-center">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, ease: "easeOut" }}
          className="flex flex-col items-center"
        >
          <h1 
            className="text-4xl md:text-5xl lg:text-6xl font-serif font-light tracking-wide mb-8 text-[#F5F2EB] leading-tight"
            style={{ textShadow: '0 4px 15px rgba(0, 0, 0, 0.5)' }}
          >
            자연스러운 빛과 머무는 시선을 담는 <br />
            서울·수도권 감성 스냅
          </h1>
          
          <p 
            className="max-w-lg mx-auto text-[#E6E2DE] mb-12 text-lg font-light leading-relaxed tracking-wide opacity-95"
            style={{ textShadow: '0 2px 10px rgba(0, 0, 0, 0.5)' }}
          >
            억지스러운 연출 없이 당신의 빛나는 찰나를 기록합니다.<br />
            개인 화보, 커플 스냅, 가족 사진까지 시간이 흘러도 변치 않는 담백한 순간을 남겨드립니다.
          </p>

          <Link 
            to="/reservation" 
            className="inline-block px-12 py-4 bg-[#F5F2EB] border border-[#F5F2EB] text-[#3A3532] text-sm tracking-[0.2em] hover:bg-transparent hover:text-[#F5F2EB] transition-all duration-500 rounded-sm font-medium shadow-lg hover:shadow-xl"
          >
            예약 문의하기
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
