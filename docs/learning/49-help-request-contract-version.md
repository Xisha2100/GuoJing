# 模块 49：求助结果契约版本

求助结果的 `schema_version` 现在由应用层常量维护，HTTP DTO 通过 `Literal` 保持严格值。Android 仍然对版本执行 fail-closed 校验；升级时必须同时更新 Python 常量、Android parser 和契约测试。
