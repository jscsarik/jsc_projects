import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Plus, Minus, Instagram } from 'lucide-react';
import { cn } from '../lib/utils';

const faqs = [
  {
    id: 1,
    question: '예약은 언제까지 해야 하나요?',
    answer: '원활한 일정 조율을 위해 최소 1주 전 예약을 권장드립니다.'
  },
  {
    id: 2,
    question: '보정본 수령까지 얼마나 걸리나요?',
    answer: '사진 셀렉 후 최종 작업까지 약 10일에서 2주 정도 소요됩니다.'
  },
  {
    id: 3,
    question: '예약금 결제는 어떻게 진행되나요?',
    answer: '사이트를 통해 예약을 접수해 주시면, 남겨주신 연락처로 예약금 입금 안내 문자를 따로 발송해 드립니다. 안내된 계좌로 입금해 주시면 예약이 최종 확정됩니다.'
  },
  {
    id: 4,
    question: '예약 취소나 변경은 어떻게 하나요?',
    answer: '원활한 스케줄 관리를 위해 촬영 3일 전까지만 일정 변경 및 예약금 100% 환불이 가능합니다. 취소 및 변경을 원하시는 경우 인스타그램 DM이나 문자로 연락해 주시기 바랍니다. 그 이후로는 취소 및 변경이 어려우니 신중한 예약 부탁드립니다.'
  },
  {
    id: 5,
    question: '촬영 장소 추천도 해주시나요?',
    answer: '네, 선호하시는 분위기를 말씀해 주시면 작가가 직접 발굴한 감성적인 스팟들을 제안해 드립니다.'
  },
  {
    id: 6,
    question: '비가 오면 촬영은 어떻게 되나요?',
    answer: '야외 촬영의 경우 기상 상황에 따라 일정을 조정하거나 따로 연락드릴 예정입니다.'
  }
];

export default function FAQ() {
  const [openId, setOpenId] = useState<number | null>(null);

  return (
    <section className="container mx-auto px-6 py-24 max-w-3xl bg-[#F5F2EB]">
      <div className="mb-20 text-center space-y-4">
        <h2 className="text-3xl md:text-4xl font-serif font-normal text-[#3A3532]">FAQ</h2>
        <p className="text-[#8C7B75] text-xs tracking-[0.2em] uppercase font-light">Frequently Asked Questions</p>
      </div>

      <div className="space-y-4">
        {faqs.map((faq) => (
          <div 
            key={faq.id} 
            className="border-b border-[#3A3532]/10 bg-transparent"
          >
            <button
              onClick={() => setOpenId(openId === faq.id ? null : faq.id)}
              className="w-full flex items-center justify-between py-6 text-left hover:opacity-70 transition-opacity"
            >
              <div className="flex items-center gap-4">
                <span className="text-[#8C7B75] font-serif italic text-lg">Q.</span>
                <span className={cn(
                  "text-base font-light tracking-wide",
                  openId === faq.id ? "text-[#8C7B75]" : "text-[#3A3532]"
                )}>
                  {faq.question}
                </span>
              </div>
              <span className={cn(
                "text-[#3A3532] transition-transform duration-300 font-light",
                openId === faq.id && "rotate-180"
              )}>
                {openId === faq.id ? <Minus size={18} strokeWidth={1} /> : <Plus size={18} strokeWidth={1} />}
              </span>
            </button>

            <AnimatePresence>
              {openId === faq.id && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: "easeInOut" }}
                  className="overflow-hidden"
                >
                  <div className="pb-8 pt-2 pl-8 text-[#5D5D5D] leading-relaxed font-light text-sm flex gap-4">
                    <span className="text-[#3A3532] font-serif italic text-lg">A.</span>
                    {faq.answer}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>

      <div className="mt-24 border-t border-[#3A3532]/10 pt-16 text-center space-y-8">
        <p className="text-[#3A3532] font-serif text-lg tracking-wide">
          찾으시는 답변이 없나요?
        </p>
        
        <a 
          href="https://www.instagram.com/ljh__flim/" 
          target="_blank" 
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center gap-3 px-10 py-4 bg-[#3A3532] text-[#F5F2EB] rounded-sm hover:bg-[#2A2522] transition-all duration-300 text-sm tracking-widest uppercase font-medium"
        >
          <Instagram size={18} strokeWidth={1.5} />
          <span>Instagram DM</span>
        </a>
      </div>
    </section>
  );
}
