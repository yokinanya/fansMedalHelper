"""
统计和报告服务模块
"""
from typing import List, Dict, Any, Optional

from .services import BaseService
from .utils import safe_get


class StatsService(BaseService):
    """统计服务"""

    def __init__(self, api, user_name: str, logger=None):
        super().__init__(api, logger)
        self.user_name = user_name
        self.coin_stats = {}  # 存储投币统计信息

    def set_coin_stats(self, coin_result: Dict[str, Any]):
        """设置投币统计信息"""
        self.coin_stats = coin_result

    def calculate_medal_stats(self, medals: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """计算勋章统计"""
        stats = {
            'full': [],      # 30
            'low': [],       # <30
            'unlit': []      # 未点亮
        }

        for medal in medals:
            today_feed = safe_get(medal, 'medal', 'today_feed', default=0)
            nick_name = safe_get(medal, 'anchor_info',
                                 'nick_name', default='未知用户')
            is_lighted = safe_get(medal, 'medal', 'is_lighted', default=1)

            if not is_lighted:
                stats['unlit'].append(nick_name)

            if today_feed >= 30:
                stats['full'].append(nick_name)
            elif today_feed < 30:
                stats['low'].append(nick_name)

        return stats

    def generate_report_messages(self, stats: Dict[str, List[str]]) -> List[str]:
        """生成统计报告消息"""
        messages = [f"【{self.user_name}】 今日亲密度获取情况如下："]

        labels = {
            'full': '【30】',
            'low': '【30以下】',
            'unlit': '【未点亮】'
        }

        for key, label in labels.items():
            name_list = stats[key]
            if name_list:
                display_names = ' '.join(name_list[:5])
                if len(name_list) > 5:
                    display_names += '等'
                messages.append(f"{label}{display_names} {len(name_list)}个")

        return messages

    def generate_coin_report(self) -> List[str]:
        """生成投币统计报告"""
        messages = []
        
        if not self.coin_stats:
            return messages
            
        success_count = self.coin_stats.get("success_count", 0)
        up_stats = self.coin_stats.get("up_stats", {})
        
        if success_count > 0:
            messages.append(f"【投币任务】成功投币 {success_count} 次")
            
            # 显示每个UP主的投币情况
            if up_stats:
                up_details = []
                for uid, stats in up_stats.items():
                    up_name = stats.get("name", f"UP主_{uid}")
                    count = stats.get("count", 0)
                    up_details.append(f"{up_name}({count}个)")
                
                if up_details:
                    # 限制显示长度，避免消息过长
                    display_details = up_details[:5]
                    if len(up_details) > 5:
                        display_details.append("等")
                    messages.append(f"【投币详情】{' '.join(display_details)}")
        
        return messages

    async def get_current_medal_info(self, initial_medal: Dict[str, Any]) -> List[str]:
        """获取当前佩戴勋章信息"""
        messages = []

        try:
            initial_medal_info = await self.api.getMedalsInfoByUid(initial_medal['target_id'])

            if initial_medal_info.get('has_fans_medal'):
                medal = initial_medal_info['my_fans_medal']
                messages.append(
                    f"【当前佩戴】「{medal['medal_name']}」({medal['target_name']}) "
                    f"{medal['level']} 级 "
                )

                if medal['today_feed'] != 0:
                    messages.extend([
                        f"今日已获取亲密度 {medal['today_feed']} (B站结算有延迟，请耐心等待)",
                    ])
        except Exception as e:
            self.log.error(f"获取当前勋章信息失败: {e}")

        return messages

    async def execute(self, medals: List[Dict[str, Any]], initial_medal: Optional[Dict[str, Any]] = None) -> List[str]:
        """生成完整的统计报告"""
        stats = self.calculate_medal_stats(medals)
        messages = self.generate_report_messages(stats)

        # 添加投币统计
        coin_messages = self.generate_coin_report()
        messages.extend(coin_messages)

        if initial_medal:
            medal_info = await self.get_current_medal_info(initial_medal)
            messages.extend(medal_info)

        return messages
