# 采集实现对比与免登录方案调查

日期：2026-10-28。这里只记录源码证据与实际结果，不将项目宣传等同于实测通过。

## 已实施的本地替换

- 浏览器：可选择系统默认、Edge、Chrome、Firefox；Edge/Chrome 优先用已安装 DrissionPage 控制本机浏览器，不需要首次下载 WebDriver。Firefox及缺少DrissionPage时仍使用Selenium，驱动可能需要下载。
- 网络：浏览器“直接连接”只设置本次专用窗口，公开评论HTTP请求不继承代理环境；不修改系统代理、VPN或TUN。不能据此保证系统层完全不经任何代理。
- 京东：公开评论API先尝试；哈希链接不猜测SKU，转真实浏览器读取；恢复评价弹层、虚拟滚动、分页及实际评论响应读取。
- 淘宝/天猫：公开rate接口先尝试；未取得评论再打开专用窗口；确认需要登录时才等待；补回评论弹层、响应读取和分页。
- 小红书：先用已存在xhs-batch-reader只读后端（关闭OCR），只接受评论，不把笔记正文当评论；无评论时由专用浏览器确认页面状态。
- 不继承旧实现关闭TLS校验、缺失评分默认五星、猜测商品ID的行为。

## 本轮验证范围

27个相关离线用例通过；7个Python及2个JS文件语法通过。Python内嵌JS有2个无效转义SyntaxWarning，尚未修改/重测。

更新服务后使用Edge+浏览器直连选项，在CSV第一条淘宝693852879255上到达真实登录页，评论0。用户随后要求先调查免登录方案，已向任务发送取消并停止批量测试器，保留记录ra_27e6c3ba202e448e；最终任务为partial、0评论、unknown原因，不能把最终失败原因直接判定为未登录。其余15条尚未开始，不宣称真实链路通过；模型费用0。

## GitHub免登录调查

| 项目 | 证据 | 结论 |
|---|---|---|
| [l010306/taobao-review-playwright](https://github.com/l010306/taobao-review-playwright) | MIT，最后推送2026-02-07；源码校验AUTH_FILE并加载storage_state；Issues当前无条目 | 首次需要扫码，不是匿名采集 |
| [Sinpensar/taobao-mcp](https://github.com/Sinpensar/taobao-mcp) | 最后推送2026-08-06；README明确要求登录，且主要是搜索/详情 | 不满足免登录评论采集；未采用，无明确许可证 |
| [a707937337/taobaocomment](https://github.com/a707937337/taobaocomment) | 最后推送2016-04-08；旧rate接口思路，README提及登录账号；无明确许可证 | 不能证明今天仍可免登录运行，不新增复制或运行旧exe |
| [UnitBytes API说明仓库](https://github.com/unitbytes/Taobao-Tmall-Alibaba-Scraper-API) | README声称Zero Login；实现示例调用Apify计费服务 | 不需用户淘宝账号的商业服务候选，不是已验证的免费本地免登录爬虫；未注册、付费或发送测试链接 |

目前未找到经过实际验证可直接替换、免费本地运行且不需要任何淘宝登录态的候选。应保留公开可读路径及真实失败原因，平台要求登录时明确提示；不能承诺换库就能匿名读取。

参考浏览器官方资料：[Microsoft Edge WebDriver](https://learn.microsoft.com/en-us/microsoft-edge/webdriver-chromium/)、[Selenium Manager](https://www.selenium.dev/documentation/selenium_manager/)。
