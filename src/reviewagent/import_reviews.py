"""Bounded CSV/XLSX/JSON imports with explicit column mapping and row errors."""
from __future__ import annotations

import csv
import io
import json
import zipfile

from reviewagent.review_data import normalize_review

MAX_UPLOAD = 8 * 1024 * 1024
ALIASES = {
    "review_text": ["review_text", "text", "content", "评论", "评论内容", "评价内容", "正文"],
    "rating": ["rating", "score", "评分", "星级"],
    "review_date": ["review_date", "date", "timestamp", "日期", "评论时间", "发布时间"],
    "platform": ["platform", "source_platform", "平台", "来源平台"],
    "source_url": ["source_url", "url", "来源链接", "原文链接"],
    "reviewer_name": ["reviewer_name", "user_id", "昵称", "用户名"],
    "review_id": ["review_id"],
    "comment_id": ["comment_id", "评论ID", "平台评论ID"],
    "product_name": ["product_name", "商品名", "产品名称"],
    "brand": ["brand", "品牌"], "model": ["model", "型号", "货号"],
    "sku": ["sku", "规格", "购买规格"],
}


def parse_upload(filename, content, mapping=None):
    if len(content) > MAX_UPLOAD:
        raise ValueError("文件超过 8 MB，请拆分后导入")
    extension = filename.lower().rsplit(".", 1)[-1]
    if extension == "xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 40 * 1024 * 1024:
                    raise ValueError("工作簿解压后过大，请导出为 CSV")
            import openpyxl
        except zipfile.BadZipFile:
            raise ValueError("XLSX 文件损坏或格式不正确") from None
        except ImportError:
            raise ValueError("未安装 Excel 支持，请安装 reviewagent[import] 或改用 CSV") from None
        try:
            book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            try:
                values = book.active.iter_rows(values_only=True)
                columns = [str(value or "").strip() for value in next(values)]
                rows = []
                for index, row in enumerate(values):
                    if index >= 5000:
                        raise ValueError("工作台单次最多 5000 行，请拆分文件")
                    rows.append(dict(zip(columns, [value.isoformat() if hasattr(value, "isoformat") else value for value in row])))
            finally:
                book.close()
        except (ValueError, StopIteration, KeyError, OSError, zipfile.BadZipFile):
            raise ValueError("工作簿为空、超过 5000 行或格式不正确") from None
    else:
        text = None
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("无法识别文件编码，请保存为 UTF-8 CSV")
        if extension == "json":
            try:
                data = json.loads(text)
            except ValueError:
                raise ValueError("JSON 格式不正确") from None
            rows = data.get("reviews", []) if isinstance(data, dict) else data
            if not isinstance(rows, list):
                raise ValueError("JSON 需为数组或含 reviews 数组的对象")
            rows = [item if isinstance(item, dict) else {"review_text": item} for item in rows]
            columns = list(dict.fromkeys(key for row in rows for key in row))
        elif extension == "csv":
            try:
                dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            try:
                reader = csv.DictReader(io.StringIO(text), dialect=dialect)
                columns = reader.fieldnames or []
                rows = []
                for index, row in enumerate(reader):
                    if index >= 5000:
                        raise ValueError("工作台单次最多 5000 行，请拆分文件")
                    rows.append(row)
            except csv.Error:
                raise ValueError("CSV 字段过长或格式不正确，请拆分长字段或重新导出") from None
        elif extension == "txt":
            rows = [{"review_text": line.strip()} for line in text.splitlines() if line.strip()]
            columns = ["review_text"]
        else:
            raise ValueError("支持 CSV、XLSX、JSON 和 TXT 文件")
    if len(rows) > 5000:
        raise ValueError("工作台单次最多 5000 行，请拆分文件")
    if not rows:
        raise ValueError("文件没有数据行")
    if not columns or len(set(columns)) != len(columns):
        raise ValueError("表头为空或重复，请给每列设置不同的名称")
    mapped = dict(mapping or {})
    lookup = {column.strip().lower(): column for column in columns}
    for target, aliases in ALIASES.items():
        if target not in mapped:
            mapped[target] = next((lookup[alias.lower()] for alias in aliases if alias.lower() in lookup), "")
    if not mapped.get("review_text"):
        return {"columns": columns, "mapping": mapped, "rows": len(rows), "reviews": [], "errors": [], "needs_mapping": True}
    if any(value and value not in columns for value in mapped.values()):
        raise ValueError("映射的列不存在")
    reviews, errors, seen = [], [], set()
    for index, row in enumerate(rows):
        item = {"raw_fields": dict(row)}
        item.update({target: row.get(column) for target, column in mapped.items() if target in ALIASES and column})
        try:
            review = normalize_review(item, index)
            if review["review_id"] in seen:
                raise ValueError("评论编号重复")
            seen.add(review["review_id"])
            reviews.append(review)
        except ValueError as exc:
            errors.append({"row": index + 2, "message": str(exc)})
    return {"columns": columns, "mapping": mapped, "rows": len(rows), "reviews": reviews,
            "errors": errors, "needs_mapping": False}
