"""Fit company-name tables without abbreviation or horizontal scrolling."""
from PySide6.QtCore import Qt,QRect
from PySide6.QtWidgets import QHeaderView,QStyle,QStyleOptionHeader

def agency_columns(view):
    model=view.model()
    return [c for c in range(model.columnCount()) if '기획사' in str(model.headerData(c,Qt.Orientation.Horizontal) or '')
        or str(model.headerData(c,Qt.Orientation.Horizontal) or '') in ('소속','상대','팀','당시 소속','정규 종료 기준 팀','현재 제안자')
        or str(model.headerData(c,Qt.Orientation.Horizontal) or '').endswith('팀')]

def text_height(metrics,text,width):
    return metrics.boundingRect(QRect(0,0,max(12,width-14),10000),Qt.TextFlag.TextWordWrap,str(text)).height()+10

class CompanyHeader(QHeaderView):
    def paintSection(self,painter,rect,logical):
        view=self.parentWidget()
        if not agency_columns(view) and not view.property('fitAllColumns'):return super().paintSection(painter,rect,logical)
        option=QStyleOptionHeader();self.initStyleOptionForIndex(option,logical)
        option.rect=rect;title=option.text;option.text=''
        painter.save();self.style().drawControl(QStyle.ControlElement.CE_Header,option,painter,self)
        painter.setPen(self.palette().text().color())
        area=rect.adjusted(5,2,-(16 if self.isSortIndicatorShown() and self.sortIndicatorSection()==logical else 5),-2)
        painter.drawText(area,Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,title);painter.restore()

def user_widths(view,columns,available,defaults):
    saved=getattr(view,'_saved_widths',{})
    if not saved or not columns:return defaults
    weights={c:max(1,saved.get(c,defaults[c])) for c in columns}
    total=sum(weights.values());minimum=min(view.horizontalHeader().minimumSectionSize(),max(1,available//len(columns)))
    room=max(0,available-minimum*len(columns))
    widths={c:minimum+int(room*weights[c]/total) for c in columns}
    for c in columns[:available-sum(widths.values())]:widths[c]+=1
    # Saved full-width layouts need no rounding or proportional changes on reload.
    if all(c in saved and saved[c]>=minimum for c in columns) and sum(saved[c] for c in columns)==available:
        return {c:saved[c] for c in columns}
    return widths

def fit_company_table(view,columns,available):
    model=view.model();companies=set(agency_columns(view))&set(columns)
    if not companies or available<=0:return None
    metrics=view.fontMetrics();header=view.horizontalHeader();n=len(columns)
    # A fixed 80px lower bound used to push wide tables beyond their viewport.
    minimum=min(32,max(12,available//max(1,n)))
    header.setMinimumSectionSize(minimum);header.setStretchLastSection(False)
    widths={}
    for c in columns:
        title=str(model.headerData(c,Qt.Orientation.Horizontal) or '')
        values=[str(model.index(r,c).data() or '') for r in range(model.rowCount())]
        natural=max([metrics.horizontalAdvance(title)+16,*[metrics.horizontalAdvance(t)+16 for t in values]])
        widths[c]=min(280,max(150,natural)) if c in companies else min(120,max(minimum,natural))
    total=sum(widths.values())
    if total>available:
        # Shrink non-company columns first; wrapping preserves every value.
        for group in ([c for c in columns if c not in companies],list(companies)):
            floor=minimum if group and group[0] not in companies else min(140,max(minimum,available//max(1,n)))
            while total>available:
                shrink=[c for c in group if widths[c]>floor]
                if not shrink:break
                for c in shrink:
                    if total<=available:break
                    widths[c]-=1;total-=1
        if total>available:
            widths={c:max(1,available//n) for c in columns}
    else:
        # Keep company names at their measured width; share spare room with other fields.
        extra=available-total;names=[c for c in columns if c not in companies]
        if not names:names=list(columns)
        for i,c in enumerate(names):widths[c]+=extra//len(names)+(i<extra%len(names))
    widths=user_widths(view,columns,available,widths)
    for c in columns:header.resizeSection(c,widths[c])
    view.setWordWrap(True);view.setTextElideMode(Qt.TextElideMode.ElideNone)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header_height=max(32,max(text_height(header.fontMetrics(),model.headerData(c,Qt.Orientation.Horizontal) or '',widths[c]-8) for c in columns))
    header.setMinimumHeight(header_height);header.setMaximumHeight(header_height)
    height=getattr(view,'_user_row_height',None) or getattr(view,'_default_row_height',32)
    for r in range(model.rowCount()):
        height=max(height,max(text_height(metrics,model.index(r,c).data() or '',widths[c]) for c in columns))
    for r in range(model.rowCount()):view.setRowHeight(r,height)
    return height

def fit_all_columns(view):
    """One continuous table: fit every field, wrapping cells instead of paging."""
    model=view.model();count=model.columnCount()
    if not count:return
    available=max(1,view.viewport().width());header=view.horizontalHeader()
    preferred=view.property('columnPreferences') or [100]*count
    if len(preferred)!=count:preferred=[100]*count
    header.setMinimumSectionSize(12);header.setStretchLastSection(False)
    widths=[max(12,int(available*w/sum(preferred))) for w in preferred]
    widths[-1]+=available-sum(widths)
    widths=user_widths(view,list(range(count)),available,dict(enumerate(widths)))
    for c,width in widths.items():
        if view.isColumnHidden(c):view.setColumnHidden(c,False)
        header.resizeSection(c,width)
    view.setWordWrap(True);view.setTextElideMode(Qt.TextElideMode.ElideNone)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    height=max(32,max(text_height(header.fontMetrics(),model.headerData(c,Qt.Orientation.Horizontal) or '',widths[c]-8) for c in range(count)))
    header.setFixedHeight(height)
    for row in range(model.rowCount()):
        view.setRowHidden(row,False)
        height=max(getattr(view,'_user_row_height',None) or getattr(view,'_default_row_height',32),max(text_height(view.fontMetrics(),model.index(row,c).data() or '',widths[c]) for c in range(count)))
        view.setRowHeight(row,height)
