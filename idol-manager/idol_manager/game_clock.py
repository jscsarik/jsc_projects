"""224-day seasons: preparation, 12 regular weeks, maintenance, 12, playoffs, offseason."""
from dataclasses import dataclass
REGULAR_WEEKS=24
OFFSEASON_WEEKS=3
POSTSEASON_WEEKS=3
DAYS_PER_WEEK=7
DAYS_PER_SEASON=224
REGULAR_START=7
MAINTENANCE_START=91
SECOND_HALF_START=98
POSTSEASON_START=182
OFFSEASON_START=203
WEEKDAY_NAMES=("월요일","화요일","수요일","목요일","금요일","토요일","일요일")

def regular_day(season,week,weekday=0):
    return (season-1)*224+7+(week-1)*7+(7 if week>=13 else 0)+weekday

@dataclass(frozen=True,order=True)
class GameDate:
    absolute_day:int=0
    def __post_init__(self):
        if type(self.absolute_day) is not int or self.absolute_day<0:raise ValueError('게임 일수는 시즌 준비 0일부터 시작합니다.')
    @property
    def season(self):return self.absolute_day//224+1
    @property
    def day_in_season(self):return self.absolute_day%224
    @property
    def overall_week(self):return self.day_in_season//7+1
    @property
    def is_preparation(self):return self.day_in_season<7
    @property
    def is_founding(self):return self.season==1 and self.is_preparation
    @property
    def is_maintenance(self):return 91<=self.day_in_season<98
    @property
    def is_regular(self):return 7<=self.day_in_season<91 or 98<=self.day_in_season<182
    @property
    def is_postseason(self):return 182<=self.day_in_season<203
    @property
    def is_offseason(self):return self.day_in_season>=203
    @property
    def week(self):
        d=self.day_in_season
        if self.is_preparation or self.is_maintenance:return 1
        if self.is_postseason:return (d-182)//7+1
        if self.is_offseason:return (d-203)//7+1
        return (d-7)//7+1 if d<91 else (d-98)//7+13
    def weekday(self):return self.absolute_day%7
    def after(self,days=1):
        if type(days) is not int or days<0:raise ValueError('진행 일수는 0 이상의 정수여야 합니다.')
        return GameDate(self.absolute_day+days)
    def __str__(self):
        phase='창단 준비' if self.is_founding else '시즌 준비' if self.is_preparation else '중간 정비' if self.is_maintenance else '정규' if self.is_regular else '포스트시즌' if self.is_postseason else '비시즌'
        return f'시즌 {self.season} · {phase} {self.week}주차 · {WEEKDAY_NAMES[self.weekday()]} (전체 {self.overall_week}/32주)'

def initialize_game_clock(connection):
    connection.execute('INSERT OR IGNORE INTO game_clock(game_id,absolute_day) SELECT 1,0 WHERE EXISTS(SELECT 1 FROM game WHERE id=1)')

def current_game_date(connection):
    setup=connection.execute("SELECT prep_day FROM founding_setup WHERE game_id=1 AND (status='active' OR (status='pending' AND protocol=2))").fetchone() if connection.execute("SELECT 1 FROM sqlite_master WHERE name='founding_setup'").fetchone() else None
    if setup:return GameDate(setup[0])
    row=connection.execute('SELECT absolute_day FROM game_clock WHERE game_id=1').fetchone()
    return GameDate(row[0]) if row else None

def is_monday(day):return day is not None and day.weekday()==0
