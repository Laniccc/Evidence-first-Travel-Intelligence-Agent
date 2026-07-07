package com.deepresearch.api.project;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface ProjectRepository extends JpaRepository<Project, String> {
    List<Project> findByUserIdOrderByCreatedAtDesc(String userId);
}
