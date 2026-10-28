# 商品与规格页备份（2026-10-29）

按用户要求暂时移除左侧“商品与规格”入口和页面实现，数据没有删除：

- 页面实现：productsView.js.txt（原 workbench-extra.js 中 productsView 函数）
- 导航入口：index-nav-products.html（原 index.html 第 19 行按钮）
- 同款检索结果弹窗原来用“去商品与规格”承载候选，现在改为在弹窗内直接列出候选链接。

## 回滚方式

```bash
git checkout backup/products-view-20261029 -- src/reviewagent/webui/workbench-extra.js src/reviewagent/webui/index.html src/reviewagent/webui/workbench.js
```

或按两个备份文件手工粘回，并把 render() 的 view 映射、标题表、command 的 view-products 分支、同款检索弹窗里的按钮恢复。

数据仍在每条分析的 candidates / object 字段里，没有迁移或清空。