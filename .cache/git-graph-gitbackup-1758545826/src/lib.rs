//! Command line tool to show clear git graphs arranged for your branching model.

use git2::Repository;
use std::path::Path;

pub mod config;
pub mod graph;
pub mod print;
pub mod settings;

pub fn get_repo<P: AsRef<Path>>(path: P) -> Result<Repository, String> {
    Repository::discover(path).map_err(|err| {
        format!(
            "ERROR: {}\n       Navigate into a repository before running git-graph, or use option --path",
            err.message()
        )
    })
}
