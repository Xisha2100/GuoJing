# 模块 45：Android 教程启动守卫

Android 在使用求助返回的计划前会比较 graph ID、revision、起始节点和每个 transition。计划引用不存在的步骤，或本地图中该步骤不是低风险，都会被拦截；服务端返回的数据不会扩大本地执行器的权限。
