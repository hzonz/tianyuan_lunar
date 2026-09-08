"""TianYuan 核心协调器 """
# 干支纪日：晚子时日柱算当天
# 干支纪年：新年以立春节气交接的时刻起算
from __future__ import annotations

import math
from datetime import time as dt_time
from datetime import datetime, date, timedelta
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.components.calendar import CalendarEvent
# 农历库
from lunar_python import Lunar, Solar

# 导入外部算法库和工具类
from .tianyuan import (
    天元日历逻辑类,
    天元农历逻辑类,
    子午流注类,
    五运六气类,
    辅行诀脏腑用药法要类,
    伤寒杂病论类,
    小六壬类,
    梅花易数类,
    皇极经世类,
    六爻占卜类,
    易经详注类,
)

# 从 cache_service 导入工业级缓存类
from .cache_service import CacheService

# 导入配置常量
from .const import (
    DOMAIN,
    LOGGER,
    CONF_REFRESH_INTERVAL,
    CONF_CUSTOM_LONGITUDE,
    CONF_ENABLE_SHUSHU,
    CONF_ENABLE_QIHUANG,
    CONF_CALC_MODE,
    CONF_BIRTHDAYS,
    MODE_ST,
    MODE_TST,
)

class TianYuanData(TypedDict):
    """天元协调器数据结构"""

    # ===== 基础时间数据 =====
    农历: Lunar
    阳历: Solar
    真太阳时: datetime
    实时模式: bool
    性别: str
    # ===== 农历相关数据 =====
    假期数据: dict[str, Any]
    节气数据: dict[str, Any]
    十二时辰数据: dict[str, Any]
    全量属性数据: dict[str, Any]
    更多农历实体数据: dict[str, Any]
    # ===== 岐黄（运气医学）相关数据 =====
    灵龟八法数据: dict[str, Any]
    纳甲筮法数据: dict[str, Any]
    纳子筮法数据: dict[str, Any]
    飞腾八法数据: dict[str, Any]
    迎随补泻数据: dict[str, Any]
    六步气机数据: dict[str, Any]
    年度运气总览数据: dict[str, Any]
    辅行诀结果数据: dict[str, Any]
    伤寒结果数据: dict[str, Any]
    # ===== 术数相关数据 =====
    小六壬数据: dict[str, Any]
    梅花易数数据: dict[str, Any]
    皇极经世数据: dict[str, Any]
    六爻爻法数据: dict[str, Any]
    # ===== 易经基础数据 =====
    易经名称数据: str
    易经信息数据: dict[str, Any]

class TianYuanCoordinator(DataUpdateCoordinator[TianYuanData]):
    """天元核心计算协调器"""

    def __init__(self, hass: HomeAssistant, entry, version: str) -> None:
        """初始化协调器"""

        self.entry = entry
        self.version = version

        self.查看日期: date | None = None
        self.性别: str = "男"
        self.选中卦名: str | None = None
        self.六爻输入字符串 = "阳阳阳阴阴阴"
        
        # --- 辅行诀联动状态 ---
        self.辅行诀选中大类 = "肝"
        self.辅行诀选中症状 = "胁下痛"
        # --- 伤寒论联动状态 ---
        self.伤寒选中六经 = "太阳"
        self.伤寒选中证型 = "太阳-表寒实"
        self.伤寒选中方名 = "麻黄汤"

        # --- 初始化高级缓存服务 (容量500) ---
        self._cache = CacheService(capacity=500)

        刷新间隔分钟 = entry.options.get(CONF_REFRESH_INTERVAL, 1)

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=刷新间隔分钟),
            config_entry=entry,
        )

    # 真太阳时计算
    def _计算真太阳时类(self, dt: datetime, 经度: float) -> datetime:
        """计算真太阳时（True Solar Time）"""

        经度偏移分钟 = (经度 - 120) * 4
        年内序号 = dt.timetuple().tm_yday
        年内角度项 = 2 * math.pi * (年内序号 - 81) / 365
        时间方程 = 9.87 * math.sin(2 * 年内角度项) - 7.53 * math.cos(年内角度项) - 1.5 * math.sin(年内角度项)

        return dt + timedelta(minutes=经度偏移分钟 + 时间方程)

    # 异步更新主入口：负责调度缓存逻辑
    async def _async_update_data(self) -> TianYuanData:
        """主计算任务：协调缓存与实时逻辑"""
        try:
            当前时间 = dt_util.now()
            实时模式 = self.查看日期 is None
            基准时间 = 当前时间 if 实时模式 else datetime.combine(self.查看日期, 当前时间.time()).replace(tzinfo=当前时间.tzinfo)

            模式 = self.entry.options.get(CONF_CALC_MODE, MODE_ST)
            经度 = float(self.entry.options.get(CONF_CUSTOM_LONGITUDE, 120.0))
            开启岐黄 = self.entry.options.get(CONF_ENABLE_QIHUANG, False)
            开启术数 = self.entry.options.get(CONF_ENABLE_SHUSHU, False)

            # 实时计算真太阳时
            标准农历 = Lunar.fromDate(基准时间)
            真太阳时 = self._计算真太阳时类(基准时间, 经度)
            真太阳时农历 = Lunar.fromDate(真太阳时)
            tst_date_str = 真太阳时.strftime('%Y-%m-%d')
            时辰名 = 真太阳时农历.getTimeZhi()

            # 获取日级缓存（key 含经度：改经度后无需依赖整集成 reload 来清空缓存）
            day_key = f"D_{tst_date_str}_{经度}_{模式}"
            日级数据 = await self._cache.get_or_set(
                day_key,
                lambda: self.hass.async_add_executor_job(self._获取同步日级基础数据类, 真太阳时, 基准时间, 模式),
                ttl=86400
            )
            数据: TianYuanData = 日级数据.copy()

            # 获取时级缓存 (仅在相关开关开启时触发)
            if 开启岐黄 or 开启术数:
                hour_key = f"H_{tst_date_str}_{时辰名}_{self.性别}_{模式}"
                时级数据 = await self._cache.get_or_set(
                    hour_key,
                    lambda: self.hass.async_add_executor_job(self._获取同步时级动态数据类, 真太阳时, 模式),
                    ttl=7200
                )
                if 时级数据:
                    # 根据开关合并数据
                    if 开启岐黄:
                        数据.update({k: v for k, v in 时级数据.items() if k in [
                            "纳甲筮法数据", "纳子筮法数据", "灵龟八法数据", "飞腾八法数据",
                            "迎随补泻数据", "六步气机数据", "年度运气总览数据"
                        ]})
                    if 开启术数:
                        数据.update({k: v for k, v in 时级数据.items() if k in [
                            "小六壬数据", "梅花易数数据", "皇极经世数据"
                        ]})

            # 实时计算与覆盖 (处理 UI 实时交互)：同步计算交给 executor，避免阻塞事件循环
            实时覆盖数据 = await self.hass.async_add_executor_job(
                self._获取同步实时覆盖数据类, 真太阳时, 标准农历, 实时模式, 数据, self.选中卦名
            )
            数据.update(实时覆盖数据)

            return 数据
        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"天元历法计算失败: {err}") from err

    def _获取同步实时覆盖数据类(self, 真太阳时: datetime, 标准农历: Lunar, 实时模式: bool, 日级数据: dict, 选中卦名: str | None) -> dict:
        """实时覆盖数据计算（同步，运行于 executor 线程）"""
        真太阳时农历 = Lunar.fromDate(真太阳时)
        # 按计算模式选择主农历，确保四柱八字（含时柱）与日级基础数据口径一致
        模式 = self.entry.options.get(CONF_CALC_MODE, MODE_ST)
        主农历 = 真太阳时农历 if 模式 == MODE_TST else 标准农历
        更多实体包 = 天元农历逻辑类.获取更多实体类(真太阳时农历, 真太阳时, self.性别)
        # 四柱八字/天干地支含时柱或时辰纳音，必须随时辰刷新：从实时主农历重算，覆盖日级缓存的冻结值
        主更多实体包 = 天元农历逻辑类.获取更多实体类(主农历, 真太阳时, self.性别)
        四柱八字包 = 主更多实体包["四柱八字数据"]
        天干地支包 = 主更多实体包["天干地支数据"]
        当前时卦名 = 日级数据.get("梅花易数数据", {}).get("state")
        显示卦名 = 选中卦名 if 选中卦名 else 当前时卦名
        return {
            "真太阳时": 真太阳时,
            "实时模式": 实时模式,
            "性别": self.性别,
            # 实时数据覆盖，确保真太阳时和时辰每分钟都在动
            "真太阳时数据": 更多实体包["真太阳时数据"],
            "十二时辰数据": 天元农历逻辑类.获取十二时辰数据类(标准农历),
            # 四柱八字含时柱，需随时辰刷新（覆盖日级缓存）
            "四柱八字数据": 四柱八字包,
            # 天干地支含时辰纳音，需随时辰刷新（覆盖日级缓存）
            "天干地支数据": 天干地支包,
            "易经名称数据": 显示卦名,
            "易经信息数据": 易经详注类.获取详注包装类(显示卦名),
            "六爻爻法数据": 六爻占卜类.执行占卜流程类(self.六爻输入字符串, 日级数据["农历"]),
            "辅行诀结果数据": 辅行诀脏腑用药法要类.辅行诀选方类(self.辅行诀选中症状),
            "伤寒结果数据": 伤寒杂病论类.获取方剂数据类(self.伤寒选中方名),
        }

    # 静态构建器：增加 模式(mode) 参数支持
    def _获取同步日级基础数据类(self, 真太阳时: datetime, 基准时间: datetime, 模式: str) -> dict:
        """日级构建器：严格遵循模式选择"""
        
        标准农历 = Lunar.fromDate(基准时间)
        真太阳时农历 = Lunar.fromDate(真太阳时)
        真太阳时阳历 = Solar.fromDate(真太阳时)
        # 模式判定：决定传感器主实体显示的“宇宙”
        主农历 = 真太阳时农历 if 模式 == MODE_TST else 标准农历
        更多实体 = 天元农历逻辑类.获取更多实体类(主农历,真太阳时,self.性别)

        return {
            "农历": 主农历,
            "阳历": 真太阳时阳历,
            "假期数据": 天元农历逻辑类.获取假期数据类(标准农历, 真太阳时阳历, 基准时间),
            "节气数据": 天元农历逻辑类.获取节气数据类(标准农历, 真太阳时阳历),
            "全量属性数据": 天元农历逻辑类.获取全量属性数据类(主农历, 真太阳时阳历),
            # 基础农历设备的更多实体（跟随模式选择）
            "四柱八字数据": 更多实体["四柱八字数据"],
            "天干地支数据": 更多实体["天干地支数据"],
            "十二天神数据": 更多实体["十二天神数据"],
            "当日冲煞数据": 更多实体["当日冲煞数据"],
            "东方星宿数据": 更多实体["东方星宿数据"],
        }

    def _获取同步时级动态数据类(self, 真太阳时: datetime, 模式: str) -> dict:
        """时级构建器：术数与岐黄动态计算"""
        # 术数和子午流注在本质上应严格基于真太阳时
        真太阳时农历 = Lunar.fromDate(真太阳时)
        真太阳时阳历 = Solar.fromDate(真太阳时)
        运气结果 = 五运六气类.全量计算类(真太阳时农历)
        
        return {
            "纳甲筮法数据": 子午流注类.纳甲法类(真太阳时农历),
            "纳子筮法数据": 子午流注类.纳子法类(真太阳时),
            "灵龟八法数据": 子午流注类.灵龟八法类(真太阳时农历, self.性别),
            "飞腾八法数据": 子午流注类.飞腾八法类(真太阳时农历),
            "迎随补泻数据": 子午流注类.迎随补泻类(真太阳时农历, 真太阳时),
            "六步气机数据": 运气结果["六步运气数据"],
            "年度运气总览数据": 运气结果["年度总览数据"],
            "小六壬数据": 小六壬类.起卦类(真太阳时农历),
            "梅花易数数据": 梅花易数类.起卦类(真太阳时农历),
            "皇极经世数据": 皇极经世类.起卦类(真太阳时农历, 真太阳时阳历),
        }

    # --- 辅行诀级联动作 ---
    async def 写入辅行诀大类类(self, 大类: str):
        self.辅行诀选中大类 = 大类
        症状列表 = 辅行诀脏腑用药法要类.获取大类症状法(大类)
        self.辅行诀选中症状 = 症状列表[0] if 症状列表 else ""
        await self.async_refresh()

    async def 写入辅行诀症状类(self, 症状: str):
        self.辅行诀选中症状 = 症状
        await self.async_refresh()

    # --- 伤寒论级联动作 ---
    async def 写入伤寒六经类(self, 六经: str):
        self.伤寒选中六经 = 六经
        证型列表 = 伤寒杂病论类.获取经下所有证型法(六经)
        if 证型列表:
            self.伤寒选中证型 = 证型列表[0]
            方名列表 = 伤寒杂病论类.获取证型下所有方名法(self.伤寒选中证型)
            if 方名列表:
                self.伤寒选中方名 = 方名列表[0]

        await self.async_refresh()

    async def 写入伤寒证型类(self, 证型: str):
        self.伤寒选中证型 = 证型
        方名列表 = 伤寒杂病论类.获取证型下所有方名法(证型)
        if 方名列表:
            self.伤寒选中方名 = 方名列表[0]
        await self.async_refresh()

    async def 写入伤寒方名类(self, 方名: str):
        self.伤寒选中方名 = 方名
        await self.async_refresh()

    async def 选择实体选卦名类(self, 卦名: str):
        self.选中卦名 = 卦名
        await self.async_refresh()

    async def 写入六爻输入类(self, value: str):
        self.六爻输入字符串 = value
        await self.async_refresh()

    def _构建单日历事件数据类(self, 单日缓存数据: dict, 目标日期: date) -> dict | None:
        """透传给逻辑引擎，包装今日历书简报"""
        return 天元日历逻辑类.包装单日摘要事件法(单日缓存数据, 目标日期)

    def _构建单生日日历事件数据类(self, 单日数据包: dict, 目标日期: date) -> dict | None:
        """透传给逻辑引擎，包装今日生日简报"""
        return 天元日历逻辑类.包装单日生日摘要类(
            目标日期, 
            单日数据包.get("农历"), # 已对齐键名
            单日数据包.get("阳历"), # 已对齐键名
            self.entry.options.get(CONF_BIRTHDAYS, [])
        )

    async def 获取日历事件范围数据类(self, 开始日期: date, 结束日期: date) -> list[CalendarEvent]:
        """批量获取并拆分多行历书事件"""
        模式 = self.entry.options.get(CONF_CALC_MODE, MODE_ST)
        采样点 = dt_time(12, 0)
        结果 = []
        
        当前日期 = 开始日期
        while 当前日期 < 结束日期:
            键 = f"D_{当前日期.strftime('%Y-%m-%d')}_{模式}"
            采样时间 = datetime.combine(当前日期, 采样点).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            
            # 从缓存获取（或计算）单日基础数据
            日数据 = await self._cache.get_or_set(
                键,
                lambda: self.hass.async_add_executor_job(self._获取同步日级基础数据类, 采样时间, 采样时间, 模式),
                ttl=86400
            )
            
            if 日数据 and "全量属性数据" in 日数据:
                # 调用逻辑引擎拆分为多行
                结果.extend(天元日历逻辑类.包装多行历书事件法(当前日期, 日数据))
                
            当前日期 += timedelta(days=1)
        return 结果

    async def 获取生日日历事件范围类(self, 开始日期: date, 结束日期: date) -> list[CalendarEvent]:
        """批量获取生日事件"""
        模式 = self.entry.options.get(CONF_CALC_MODE, MODE_ST)
        生日配置 = self.entry.options.get(CONF_BIRTHDAYS, [])
        采样点 = dt_time(12, 0)
        结果 = []
        
        当前日期 = 开始日期
        while 当前日期 < 结束日期:
            键 = f"D_{当前日期.strftime('%Y-%m-%d')}_{模式}"
            采样时间 = datetime.combine(当前日期, 采样点).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            
            日数据 = await self._cache.get_or_set(
                键,
                lambda: self.hass.async_add_executor_job(self._获取同步日级基础数据类, 采样时间, 采样时间, 模式),
                ttl=86400
            )
            
            if 日数据:
                # 调用逻辑引擎检测生日，并传入对齐的对象键名
                结果.extend(天元日历逻辑类.检测并包装生日事件集类(
                    当前日期, 
                    日数据.get("农历"),
                    日数据.get("阳历"),
                    生日配置
                ))
                
            当前日期 += timedelta(days=1)
        return 结果

    # 设备与集成属性
    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            translation_key="tianyuan_lunar",
            manufacturer="TianYuan Calendar",
            sw_version=str(self.version),
            entry_type="service",
            configuration_url="https://github.com/PraxiGEN/ha_tianyuan_calendar",
            model="察日月之度，定岁时之序。",
        )

    @property
    def qihuang_device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.entry.entry_id}_qihuang")},
            translation_key="tianyuan_qihuang",
            manufacturer="TianYuan Calendar",
            sw_version=str(self.version),
            entry_type="service",
            via_device=(DOMAIN, self.entry.entry_id),
            model="法于阴阳，和于术数，以通天人之纪。",
        )   

    @property
    def shushu_device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.entry.entry_id}_shushu")},
            translation_key="tianyuan_shushu",
            manufacturer="TianYuan Calendar",
            sw_version=str(self.version),
            entry_type="service",
            via_device=(DOMAIN, self.entry.entry_id),
            model="观天之道，执天之行，尽矣。",
        )