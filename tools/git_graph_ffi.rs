// Rust 端 FFI 接口定义
// 文件：src/git-graph/src/ffi.rs

use std::ffi::{CStr, CString};
use std::os::raw::c_char;
use serde_json;

/// FFI 接口：生成 JSON 格式的图形布局
#[no_mangle]
pub extern "C" fn git_graph_layout_json(
    repo_path: *const c_char,
    limit: usize,
) -> *mut c_char {
    let path = unsafe {
        if repo_path.is_null() {
            return std::ptr::null_mut();
        }
        match CStr::from_ptr(repo_path).to_str() {
            Ok(s) => s,
            Err(_) => return std::ptr::null_mut(),
        }
    };

    // 调用内部函数生成布局
    match generate_layout(path, limit) {
        Ok(json) => {
            match CString::new(json) {
                Ok(c_str) => c_str.into_raw(),
                Err(_) => std::ptr::null_mut(),
            }
        }
        Err(_) => std::ptr::null_mut(),
    }
}

/// FFI 接口：释放字符串内存
#[no_mangle]
pub extern "C" fn git_graph_free_string(s: *mut c_char) {
    if !s.is_null() {
        unsafe {
            let _ = CString::from_raw(s);
        }
    }
}

// 内部实现函数
fn generate_layout(repo_path: &str, limit: usize) -> Result<String, Box<dyn std::error::Error>> {
    use git2::Repository;

    let repo = Repository::open(repo_path)?;
    let mut revwalk = repo.revwalk()?;
    revwalk.push_head()?;
    revwalk.set_sorting(git2::Sort::TOPOLOGICAL)?;

    let mut nodes = Vec::new();
    let mut edges = Vec::new();
    let mut lanes = Vec::new();
    let mut current_lane = 0;

    // 简化的布局算法
    for (idx, oid) in revwalk.enumerate() {
        if idx >= limit {
            break;
        }

        let oid = oid?;
        let commit = repo.find_commit(oid)?;

        // 分配 lane (列)
        let lane = if commit.parent_count() > 1 {
            // 合并提交
            current_lane = (current_lane + 1) % 3;
            current_lane
        } else {
            0 // 主线
        };

        // 创建节点
        let node = serde_json::json!({
            "index": idx,
            "id": oid.to_string(),
            "short": &oid.to_string()[..7],
            "column": lane,
            "subject": commit.summary().unwrap_or(""),
            "author": commit.author().name().unwrap_or(""),
            "timestamp": commit.time().seconds(),
            "is_merge": commit.parent_count() > 1,
        });
        nodes.push(node);

        // 创建边
        for parent in commit.parent_ids() {
            edges.push(serde_json::json!({
                "from": idx,
                "to_id": parent.to_string(),
            }));
        }
    }

    // 解析边的目标索引
    let mut resolved_edges = Vec::new();
    for edge in edges {
        if let Some(to_id) = edge["to_id"].as_str() {
            for (idx, node) in nodes.iter().enumerate() {
                if node["id"].as_str() == Some(to_id) {
                    resolved_edges.push(serde_json::json!({
                        "from": edge["from"],
                        "to": idx,
                    }));
                    break;
                }
            }
        }
    }

    let result = serde_json::json!({
        "nodes": nodes,
        "edges": resolved_edges,
        "metadata": {
            "repo_path": repo_path,
            "limit": limit,
            "total_nodes": nodes.len(),
        }
    });

    Ok(serde_json::to_string(&result)?)
}