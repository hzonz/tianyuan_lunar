"""天元历法引擎 - 处理农历、假期、节气及实体属性组装."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from lunar_python import Lunar, Solar, LunarTime
from lunar_python.util import HolidayUtil

class 天元农历逻辑类:
    """农历核心逻辑处理类"""

    @staticmethod
    def 获取假期数据类(农历: Lunar, 阳历: Solar, dt: datetime) -> dict:
        """计算假期与节日信息"""
        假期 = HolidayUtil.getHoliday(dt.year, dt.month, dt.day)
        状态 = "工作日" if 假期 is None or 假期.isWork() else 假期.getName()

        法定名称 = ""
        是否工作日 = "是"
        假期标签 = ""
        
        if 假期:
            是否工作日 = "是" if (假期 is None or 假期.isWork()) else "否"
            if 假期.isWork():
                # 调休上班
                法定名称 = f"{假期.getName()}调休"
                假期标签 = f"[班] {假期.getName()}调休"
            else:
                # 法定放假
                法定名称 = 假期.getName()
                假期标签 = f"[假] {假期.getName()}"
        else:
            # 无国家法定安排，按周末判定
            周几 = 阳历.getWeek() # 0-6，0是周日
            是否工作日 = "否" if 周几 == 0 or 周几 == 6 else "是"
            
        # 如果是法定特日，状态显示具体名称；否则显示 工作日/休息日
        if 法定名称:
            状态 = 法定名称
        else:
            状态 = "工作日" if 是否工作日 == "是" else "休息日"

        阳历节日 = 阳历.getFestivals()
        农历节日 = 农历.getFestivals()
        # 合并所有节日，过滤掉占位符
        全部节日 = [f for f in (阳历节日 + 农历节日)]
        
        # 构造用于月历格子的显示列表 (带 [假][班] 前缀)
        显示列表 = []
        if 假期标签:
            显示列表.append(假期标签)
        
        for f in 全部节日:
            # 避开与法定名称重复的节日 (例如 5月1日 既是法定也是阳历节日)
            if 假期 and f == 假期.getName():
                continue
            显示列表.append(f)

        节日列表 = []
        for 偏移天数 in range(-42, 43):
            if 偏移天数 == 0: continue
            阳历日 = 阳历.next(偏移天数)
            农历日 = 农历.next(偏移天数)
            法定 = HolidayUtil.getHoliday(阳历日.getYear(), 阳历日.getMonth(), 阳历日.getDay())

            if 法定 and not 法定.isWork():
                节日列表.append({"name": 法定.getName(), "days": 偏移天数, "date": 阳历日.toYmd(), "type": "法定假期"})
            for f in 阳历日.getFestivals():
                节日列表.append({"name": f, "days": 偏移天数, "date": 阳历日.toYmd(), "type": "阳历节日"})
            for f in 农历日.getFestivals():
                节日列表.append({"name": f, "days": 偏移天数, "date": 农历日.getSolar().toYmd(), "type": "农历节日"})

        return {
            "state": 状态,
            "显示列表": 显示列表,
            "是否工作日": 是否工作日,
            "attributes": {
                "当天节日": {
                    "阳历节日": 阳历.getFestivals() or ["无阳历节日"],
                    "农历节日": 农历.getFestivals() or ["无农历节日"],
                },
                "假期信息": {
                    "名称": 假期.getName() if 假期 else "无假期",
                    "类型": "法定节假日" if 假期 and not 假期.isWork() else "工作日",
                    "是否工作日": 是否工作日,
                },
                "最近节日": sorted(节日列表, key=lambda x: abs(x["days"]))[:10],
            }
        }

    @staticmethod
    def 获取节气数据类(农历: Lunar, 阳历: Solar) -> dict:
        """计算节气倒计时"""
        当前 = 农历.getCurrentJieQi()
        下一 = 农历.getNextJieQi()
        上一 = 农历.getPrevJieQi()
        
        下一日期 = datetime.strptime(下一.getSolar().toYmd(), "%Y-%m-%d")
        上一日期 = datetime.strptime(上一.getSolar().toYmd(), "%Y-%m-%d")

        当前日期 = datetime.strptime(阳历.toYmd(), "%Y-%m-%d")
        天数至下一 = (下一日期 - 当前日期).days # 距离下一节气还有几天
        天数后上一 = (当前日期 - 上一日期).days # 距离上一节气已过几天

        干净节气名 = 当前.getName() if 当前 else "" 
        状态 = f"今天是{当前.getName()}" if 当前 else f"{天数至下一}天后是{下一.getName()}"
        return {
            "state": 状态,
            "节气名": 干净节气名,
            "attributes": {
                "上一节气": f"{上一.getName()} {上一.getSolar().toYmd()}",
                "下一节气": f"{下一.getName()} {下一.getSolar().toYmd()}",
                "已过天数": f"{上一.getName()}后第{天数后上一}天"
            }
        }

    @staticmethod
    def 获取十二时辰数据类(农历: Lunar) -> dict:
        """计算十二时辰全表"""
        配置 = [
            ("早子时", 0), ("丑时", 1), ("寅时", 3), ("卯时", 5), ("辰时", 7),
            ("巳时", 9), ("午时", 11), ("未时", 13), ("申时", 15),
            ("酉时", 17), ("戌时", 19), ("亥时", 21), ("晚子时", 23),
        ]
        时辰结果 = {}
        for 名称, 小时 in 配置:
            lt = LunarTime.fromYmdHms(农历.getYear(), 农历.getMonth(), 农历.getDay(), 小时, 0, 0)
            if 名称 == "早子时": 时间范围 = "00:00 - 00:59"
            elif 名称 == "晚子时": 时间范围 = "23:00 - 23:59"
            else: 时间范围 = f"{lt.getMinHm()} - {lt.getMaxHm()}"

            时辰结果[名称] = {
                "时间": 时间范围,
                "干支": lt.getGanZhi(),
                "十二天神": f"{lt.getTianShen()}({lt.getTianShenType()}) {lt.getTianShenLuck()}",
                "吉凶": lt.getTianShenLuck(),
                "冲煞": f"冲{lt.getChongDesc()} 煞{lt.getSha()}",
                "宜": ". ".join(lt.getYi()) if lt.getYi() else "无",
                "忌": ". ".join(lt.getJi()) if lt.getJi() else "无",
            }
        return {"state": f"{农历.getTimeZhi()}时", "attributes": 时辰结果}
        
    @staticmethod
    def 计算生肖动合关系类(zhi: str) -> dict[str, str]:
        """计算地支动合关系"""
        关系表 = {
            "子": {"六合": "牛", "三合": "猴 龙", "相冲": "马", "相刑": "兔", "相害": "羊", "相破": "鸡"},
            "丑": {"六合": "鼠", "三合": "蛇 鸡", "相冲": "羊", "相刑": "狗", "相害": "马", "相破": "龙"},
            "寅": {"六合": "猪", "三合": "马 狗", "相冲": "猴", "相刑": "蛇 猴", "相害": "蛇", "相破": "猪"},
            "卯": {"六合": "狗", "三合": "猪 羊", "相冲": "鸡", "相刑": "鼠", "相害": "龙", "相破": "马"},
            "辰": {"六合": "鸡", "三合": "猴 鼠", "相冲": "狗", "相刑": "龙(自刑)", "相害": "兔", "相破": "牛"},
            "巳": {"六合": "猴", "三合": "鸡 牛", "相冲": "猪", "相刑": "虎 猴", "相害": "虎", "相破": "猴"},
            "午": {"六合": "羊", "三合": "虎 狗", "相冲": "鼠", "相刑": "马(自刑)", "相害": "牛", "相破": "兔"},
            "未": {"六合": "马", "三合": "猪 兔", "相冲": "丑", "相刑": "狗 丑", "相害": "鼠", "相破": "狗"},
            "申": {"六合": "蛇", "三合": "鼠 龙", "相冲": "寅", "相刑": "虎 巳", "相害": "猪", "相破": "蛇"},
            "酉": {"六合": "龙", "三合": "蛇 牛", "相冲": "卯", "相刑": "酉(自刑)", "相害": "狗", "相破": "鼠"},
            "戌": {"六合": "兔", "三合": "虎 马", "相冲": "龙", "相刑": "牛 未", "相害": "鸡", "相破": "羊"},
            "亥": {"六合": "寅", "三合": "兔 羊", "相冲": "蛇", "相刑": "亥(自刑)", "相害": "猴", "相破": "虎"},
        }
        return 关系表.get(zhi, {"六合": "无", "三合": "无", "相冲": "无", "相刑": "无", "相害": "无", "相破": "无"})

    @staticmethod
    def 获取更多实体类(农历: Lunar, 真太阳时: datetime, 性别: str) -> dict:
        """组装更多农历扩展实体"""
        八字 = 农历.getEightChar()
        关系 = 天元农历逻辑类.计算生肖动合关系类(农历.getDayZhiExact2())
        
        return {
            "真太阳时数据": {
                "state": f"{农历.getTimeZhi()}时",
                "attributes": {
                    "农历": f"{农历.getMonthInChinese()}月{农历.getDayInChinese()}",
                    "八字": 农历.getEightChar().toString(),
                    "十二天神": f"{农历.getTimeTianShen()}({农历.getTimeTianShenType()}) {农历.getTimeTianShenLuck()}",
                    "冲煞": f"冲{农历.getTimeChongDesc()} 煞{农历.getTimeSha()}",
                    "宜": ". ".join(农历.getTimeYi()) if 农历.getTimeYi() else "无",
                    "忌": ". ".join(农历.getTimeJi()) if 农历.getTimeJi() else "无",
                    "太阳时": 真太阳时.strftime("%H:%M")
                }
            },
            "四柱八字数据": {
                "state": 八字.toString(),
                "attributes": {
                    "五行": f"{八字.getYearWuXing()}, {八字.getMonthWuXing()}, {八字.getDayWuXing()}, {八字.getTimeWuXing()}",
                    "纳音": f"{八字.getYearNaYin()}, {八字.getMonthNaYin()}, {八字.getDayNaYin()}, {八字.getTimeNaYin()}",
                    "十神": f"{八字.getYearShiShenGan()}, {八字.getMonthShiShenGan()}, {八字.getDayShiShenGan()}, {八字.getTimeShiShenGan()}",
                    "地势": f"{八字.getYearDiShi()}, {八字.getMonthDiShi()}, {八字.getDayDiShi()}, {八字.getTimeDiShi()}",
                    "其他": {"胎元": 八字.getTaiYuan(), "命宫": 八字.getMingGong(), "身宫": 八字.getShenGong()}
                }
            },
            "天干地支数据": {
                "state": f"{农历.getYearInGanZhiExact()}年 {农历.getMonthInGanZhiExact()}月 {农历.getDayInGanZhiExact()}日",
                "attributes": {
                    "干支": {
                        "年": f"{农历.getYearInGanZhiExact()}年",
                        "月": f"{农历.getMonthInGanZhiExact()}月",
                        "日": f"{农历.getDayInGanZhiExact2()}日"
                    },
                    "纳音": {"年": 农历.getYearNaYin(), "月": 农历.getMonthNaYin(), "日": 农历.getDayNaYin(), "时": 农历.getTimeNaYin()},
                    "生肖": {"年": 农历.getYearShengXiaoExact(), "月": 农历.getMonthShengXiaoExact(), "日": 农历.getDayShengXiao(), "时": 农历.getTimeShengXiao()}
                }
            },
            "十二天神数据": {
                "state": f"{农历.getDayTianShen()}({农历.getDayTianShenType()}) {农历.getDayTianShenLuck()}",
                "attributes": {
                    "择日法": "青龙明堂与天刑，朱雀金贵天德神； 白虎玉堂天牢黑，玄武司命惊勾陈。",
                    "诀曰": "道远几时通达，路遥何日还乡。"
                }
            },
            "当日冲煞数据": {
                "state": f"{农历.getDayShengXiao()}日 冲{农历.getDayChongDesc()} 煞{农历.getDaySha()}",
                "attributes": {"当日生肖": 农历.getDayShengXiao(), **关系}
            },
            "东方星宿数据": {
                "state": f"{农历.getGong()}方{农历.getXiu()}{农历.getZheng()}{农历.getAnimal()}-{农历.getXiuLuck()}",
                "attributes": {"歌诀": 农历.getXiuSong()}
            }
        }

    @staticmethod
    def 获取全量属性数据类(l: Lunar, s: Solar) -> dict[str, Any]:
        """构建全量农历属性字段"""
        return {
            "农历": f"{l.getMonthInChinese()}月{l.getDayInChinese()}",
            "星期": f"星期{l.getWeekInChinese()}",
            "天干地支": f"{l.getYearInGanZhiExact()}{l.getYearShengXiaoExact()}年 {l.getMonthInGanZhiExact()}月 {l.getDayInGanZhiExact2()}日",
            "日禄": l.getDayLu(),
            "物候": f"{l.getHou()} {l.getWuHou()}",
            "六曜": l.getLiuYao(),
            "七曜": l.getZheng(),
            "东方星宿": f"{l.getGong()}方{l.getXiu()}{l.getZheng()}{l.getAnimal()}-{l.getXiuLuck()}",
            "彭祖干": l.getPengZuGan(),
            "彭祖支": l.getPengZuZhi(),
            "吉神方位": {
                "喜神": f"{l.getDayPositionXi()} {l.getDayPositionXiDesc()}",
                "阳贵": f"{l.getDayPositionYangGui()} {l.getDayPositionYangGuiDesc()}",
                "阴贵": f"{l.getDayPositionYinGui()} {l.getDayPositionYinGuiDesc()}",
                "福神": f"{l.getDayPositionFu()} {l.getDayPositionFuDesc()}",
                "财神": f"{l.getDayPositionCai()} {l.getDayPositionCaiDesc()}"
            },
            "太岁": f"{l.getDayPositionTaiSui(2)} {l.getDayPositionTaiSuiDesc(2)}",
            "胎神": l.getDayPositionTai(),
            "冲煞": f"{l.getDayShengXiao()}日 冲{l.getDayChongDesc()} 煞{l.getDaySha()}",
            "八字": l.getEightChar().toString(),
            "建除日": f"{l.getDayNaYin()} {l.getZhiXing()}执位",
            "十二天神": f"{l.getDayTianShen()}({l.getDayTianShenType()}) {l.getDayTianShenLuck()}",
            "宜": ". ".join(l.getDayYi()),
            "忌": ". ".join(l.getDayJi()),
            "吉神": ". ".join(l.getDayJiShen()),
            "凶煞": ". ".join(l.getDayXiongSha()),
            "月相": f"{l.getYueXiang()}月",
            "季节": l.getSeason(),
            "九星": l.getDayNineStar().toFullString()
        }