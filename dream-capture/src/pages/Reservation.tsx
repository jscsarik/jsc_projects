import { useState } from 'react';
import { motion } from 'motion/react';
import { Calendar, ChevronDown } from 'lucide-react';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';

export default function Reservation() {
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);

  // 1. 날짜 기준점: 오늘
  const today = new Date();
  today.setHours(0, 0, 0, 0); 
  
  // 2. 예약 가능 마지막 날짜: 오늘 포함 3주 (오늘 날짜 + 20일)
  const maxAvailableDate = new Date(today);
  maxAvailableDate.setDate(today.getDate() + 20);

  // 3. 수동 마감 날짜 세팅 (월은 0부터 시작, 2 = 3월)
  const blockedDates = [
    new Date(2026, 2, 25)
  ];

  // 4. 월/화요일 차단
  const isSelectableDate = (date: Date) => {
    const day = date.getDay();
    return day !== 1 && day !== 2; // 월(1), 화(2) 차단
  };

  return (
    <section className="container mx-auto px-6 py-24 bg-[#F5F2EB]">
      <div className="mb-16 text-center space-y-4">
        <h2 className="text-3xl md:text-4xl font-serif font-normal text-[#2A2522]">예약 안내</h2>
        <p className="text-[#8C7B75] text-xs tracking-[0.2em] uppercase font-light">Reservation</p>
      </div>

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="max-w-xl mx-auto"
      >
        <form 
          action="https://formsubmit.co/0921l@naver.com" 
          method="POST" 
          className="space-y-8"
        >
          {/* Hidden Captcha Field */}
          <input type="hidden" name="_captcha" value="false" />

          {/* Name */}
          <div className="space-y-2">
            <label htmlFor="name" className="text-xs tracking-widest text-[#5D5D5D] uppercase">Name</label>
            <input
              type="text"
              id="name"
              name="성함"
              required
              placeholder="성함"
              className="w-full bg-transparent border-b border-[#3A3532]/20 px-2 py-3 text-[#3A3532] placeholder:text-[#3A3532]/30 focus:outline-none focus:border-[#8C7B75] transition-colors font-light"
            />
          </div>

          {/* Contact */}
          <div className="space-y-2">
            <label htmlFor="contact" className="text-xs tracking-widest text-[#5D5D5D] uppercase">Contact</label>
            <input
              type="tel"
              id="contact"
              name="연락처"
              required
              placeholder="연락처"
              className="w-full bg-transparent border-b border-[#3A3532]/20 px-2 py-3 text-[#3A3532] placeholder:text-[#3A3532]/30 focus:outline-none focus:border-[#8C7B75] transition-colors font-light"
            />
          </div>

          {/* Date (3주 연장 및 안내 문구 추가) */}
          <div className="space-y-2">
            <label htmlFor="date" className="text-xs tracking-widest text-[#5D5D5D] uppercase">Preferred Date</label>
            <div className="relative">
              <DatePicker
                selected={selectedDate}
                onChange={(date) => setSelectedDate(date)}
                minDate={today} // 오늘부터
                maxDate={maxAvailableDate} // 3주까지만
                excludeDates={blockedDates}
                filterDate={isSelectableDate} // 월/화 차단
                dateFormat="yyyy-MM-dd"
                placeholderText="날짜를 선택해주세요"
                className="w-full bg-transparent border-b border-[#3A3532]/20 px-2 py-3 text-[#3A3532] placeholder:text-[#3A3532]/30 focus:outline-none focus:border-[#8C7B75] transition-colors font-light"
                wrapperClassName="w-full"
                required
              />
              <input 
                type="hidden" 
                name="촬영날짜" 
                value={selectedDate ? selectedDate.toISOString().split('T')[0] : ''} 
              />
              <Calendar className="absolute right-2 top-1/2 -translate-y-1/2 text-[#3A3532]/40 pointer-events-none" size={16} />
            </div>
            {/* 친절한 안내 문구 추가 */}
            <p className="text-[#8C7B75] text-[11px] mt-2 font-light tracking-wide">
              * 금일 기준 3주 이내 예약 가능 (매주 월/화요일은 선택 불가)
            </p>
          </div>

          {/* Package */}
          <div className="space-y-2">
            <label htmlFor="package" className="text-xs tracking-widest text-[#5D5D5D] uppercase">Package</label>
            <div className="relative">
              <select
                id="package"
                name="상품선택"
                required
                defaultValue=""
                className="w-full bg-transparent border-b border-[#3A3532]/20 px-2 py-3 text-[#3A3532] focus:outline-none focus:border-[#8C7B75] transition-colors appearance-none font-light"
              >
                <option value="" disabled>상품을 선택해주세요</option>
                <option value="BASIC 스냅 (40,000원)">BASIC 스냅 (40,000원)</option>
                <option value="STANDARD 스냅 (60,000원)">STANDARD 스냅 (60,000원)</option>
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 text-[#3A3532]/40 pointer-events-none" size={16} />
            </div>
          </div>

          {/* Concept */}
          <div className="space-y-2">
            <label htmlFor="concept" className="text-xs tracking-widest text-[#5D5D5D] uppercase">Concept</label>
            <div className="relative">
              <select
                id="concept"
                name="촬영컨셉"
                required
                defaultValue=""
                className="w-full bg-transparent border-b border-[#3A3532]/20 px-2 py-3 text-[#3A3532] focus:outline-none focus:border-[#8C7B75] transition-colors appearance-none font-light"
              >
                <option value="" disabled>촬영 컨셉 선택</option>
                <option value="개인 화보">개인 화보</option>
                <option value="커플/데이트 스냅">커플/데이트 스냅</option>
                <option value="가족 사진">가족 사진</option>
                <option value="돌스냅/아기 사진">돌스냅/아기 사진</option>
                <option value="기타 문의">기타 문의</option>
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 text-[#3A3532]/40 pointer-events-none" size={16} />
            </div>
          </div>

          {/* Region */}
          <div className="space-y-2">
            <label htmlFor="region" className="text-xs tracking-widest text-[#5D5D5D] uppercase">Region</label>
            <div className="relative">
              <select
                id="region"
                name="지역"
                required
                defaultValue=""
                className="w-full bg-transparent border-b border-[#3A3532]/20 px-2 py-3 text-[#3A3532] focus:outline-none focus:border-[#8C7B75] transition-colors appearance-none font-light"
              >
                <option value="" disabled>희망 지역 선택</option>
                <option value="서울">서울</option>
                <option value="경기">경기</option>
                <option value="인천">인천</option>
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 text-[#3A3532]/40 pointer-events-none" size={16} />
            </div>
          </div>

          {/* Detailed Location */}
          <div className="space-y-2">
            <label htmlFor="location_detail" className="text-xs tracking-widest text-[#5D5D5D] uppercase">Detailed Location</label>
            <input
              type="text"
              id="location_detail"
              name="상세장소"
              placeholder="예: 올림픽공원, 홍대입구역, 특정 스튜디오 등"
              className="w-full bg-transparent border-b border-[#3A3532]/20 px-2 py-3 text-[#3A3532] placeholder:text-[#3A3532]/30 focus:outline-none focus:border-[#8C7B75] transition-colors font-light"
            />
          </div>

          {/* Message */}
          <div className="space-y-2">
            <label htmlFor="message" className="text-xs tracking-widest text-[#5D5D5D] uppercase">Message</label>
            <textarea
              id="message"
              name="남기실말씀"
              rows={5}
              placeholder="문의하실 내용을 자유롭게 남겨주세요."
              className="w-full bg-transparent border border-[#3A3532]/20 rounded-sm px-4 py-4 text-[#3A3532] placeholder:text-[#3A3532]/30 focus:outline-none focus:border-[#8C7B75] transition-colors resize-none font-light"
            />
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            className="w-full bg-[#3A3532] text-[#F5F2EB] font-light py-4 rounded-sm text-sm tracking-widest hover:bg-[#2A2522] transition-colors mt-8 flex items-center justify-center gap-2 uppercase"
          >
            <span>예약 문의하기</span>
          </button>
        </form>
      </motion.div>
    </section>
  );
}
