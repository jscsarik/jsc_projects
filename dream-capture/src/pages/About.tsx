import { motion } from 'motion/react';
import { Instagram, MessageCircle } from 'lucide-react';

export default function About() {
  return (
    <section className="container mx-auto px-6 py-24 bg-[#F5F2EB]">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-16 md:gap-24 items-center max-w-5xl mx-auto">
        {/* Profile Image */}
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1 }}
          className="relative aspect-[4/5] md:aspect-[3/4]"
        >
          <div className="w-full h-full overflow-hidden bg-[#E6E2DE]">
            <img 
              src="/me.jpg" 
              alt="Photographer" 
              className="w-full h-full object-cover"
              referrerPolicy="no-referrer"
            />
          </div>
        </motion.div>

        {/* Bio Content */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, delay: 0.3 }}
          className="space-y-12"
        >
          <div className="space-y-6">
            <h2 className="text-3xl font-serif font-normal text-[#2A2522] tracking-tight">
              안녕하세요.<br/>
              이재호 필름입니다.
            </h2>
            <div className="w-12 h-[1px] bg-[#8C7B75]/50" />
            <p className="text-lg font-serif text-[#5D5D5D] italic tracking-wide">
              "자연스러운 빛과 머무는 시선을 담습니다."
            </p>
          </div>

          <div className="space-y-6 text-[#4A4542] leading-loose font-light text-sm md:text-base tracking-wide text-justify">
            <p>
              과장된 연출이나 인위적인 포즈는 배제합니다. 
              당신이 머무는 그 공간, 그날의 온도와 분위기가 
              사진 속에 온전히 스며들도록 차분하게 기록합니다.
            </p>
            <p>
              시간이 지나고 다시 꺼내 보아도 촌스럽지 않은, 
              담백하고 따뜻한 순간을 남겨드립니다.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row gap-5 pt-4">
            <a 
              href="https://www.instagram.com/ljh__flim/" 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-3 px-8 py-3.5 border border-[#3A3532]/20 text-[#3A3532] rounded-sm hover:bg-[#3A3532] hover:text-[#F5F2EB] transition-all duration-300 text-xs tracking-widest uppercase"
            >
              <Instagram size={16} strokeWidth={1.5} />
              <span>Instagram</span>
            </a>
            
            <a 
              href="https://open.kakao.com/o/sdLSY4Xh" 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-3 px-8 py-3.5 bg-[#3A3532] text-[#F5F2EB] rounded-sm hover:bg-[#2A2522] transition-all duration-300 text-xs tracking-widest uppercase"
            >
              <MessageCircle size={16} strokeWidth={1.5} />
              <span>Contact</span>
            </a>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
