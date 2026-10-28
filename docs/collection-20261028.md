# 天猫/淘宝评论采集：2026-10-28 验证记录

这里记录本轮真实链路的事实和结论，结论对应的都是本机实际运行结果，不是推测。

## 问题

天猫商品页初始只渲染 2 条预览评价。此前的采集用脚本点击“查看全部评价”（`element.click()`），
页面没有响应，只采到 2 条，最终记为 partial / no_review_text。

## 根因（实测）

1. “查看全部评价”的点击处理挂在子元素 `[class*="ShowButton"]` 上，外层是文字容器。
   对容器做脚本点击不会触发 React 处理器，页面不展开。
2. 改用 CDP 真鼠标事件（`Input.dispatchMouseEvent`）点击后，评论从 2 条展开到 13 条。
3. 页面同时请求 `mtop.taobao.rate.detaillist.get`（h5api.m.tmall.com），返回 11 条结构化评价。
4. 页面标注“用户评价·33”，其中 22 条属于“已折叠22条对你帮助不大的评价”，默认列表不展示。
5. 该接口接受 `foldFlag` 参数：`0` 返回主列表（11 条，total 11），`1` 返回折叠列表（20+2 条，total 22）。
   `pageNo` 递增可分页，单页 20 条。

## 实现

- `browser_session._CdpDriver.click_at(x, y)`：通过 CDP 派发可信鼠标事件；无 CDP 的浏览器保留脚本点击回退。
- `browser_collection._find_comment_entry`：按文字匹配取**最内层**元素并返回点击坐标；
  `_open_comments` 先真点击，失败再回退。
- `browser_collection._tmall_rate_rows`：在页面上下文调用 `lib.mtop.request`，
  依次取 `foldFlag=0` 与 `foldFlag=1` 的分页数据，直到空页或达到上限。
- `public_collection.normalize_comment`：补认 `feedbackDate`、`createTime`、`userNick`、`skuValueStr`。
- 只有星级、正文是平台占位文案（“该用户觉得商品非常好，给出5星好评”等）的评价不计入文本证据，
  数量记入采集缺口说明（`rating_only`）。

## 实测结果

| 项目 | 结果 |
| --- | --- |
| 页面显示评价数 | 33 |
| 主列表接口 | 11 条 |
| 折叠列表接口 | 22 条（20 + 2） |
| 合计可取得 | 33 条 |
| 其中只有星级、无正文 | 19 条 |
| 作为文本证据保留 | 14 条 |
| 采集缺口 | “另有 19 条评价只有星级、没有买家正文”，原因已确认，不循环重试 |
| 记录 | `ra_449f83dac73b44cf`（33 条原始）、`ra_5353ff74a46a4e09`（14 条正文 + 缺口说明） |

采集到的 14 条正文每条都带发布日期、用户名和规格；同一原文的多条折叠评价按 comment_id 去重。
页面标注 33 条时，不会为了凑数重复写入同一段文字。

## 边界

- 只有详情页暴露 `lib.mtop` 时才能走分页接口；否则退回 DOM 展开，仍按实际可见条数采集并标注缺口。
- 登录/身份校验仍由用户在专用窗口完成；本流程不破解验证码、不轮换 Cookie 绕过限制。
- 淘宝（item.taobao.com）主链路复用同一实现，本轮未在淘宝详情链接上复测。
