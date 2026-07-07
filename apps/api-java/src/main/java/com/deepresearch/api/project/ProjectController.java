package com.deepresearch.api.project;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/projects")
public class ProjectController {

    private final ProjectRepository projectRepository;

    public ProjectController(ProjectRepository projectRepository) {
        this.projectRepository = projectRepository;
    }

    @GetMapping
    public List<Project> list(Authentication auth) {
        return projectRepository.findByUserIdOrderByCreatedAtDesc(auth.getName());
    }

    @PostMapping
    public Project create(@RequestBody Map<String, String> body, Authentication auth) {
        Project project = new Project(
            auth.getName(),
            body.getOrDefault("title", "Untitled"),
            body.getOrDefault("query", "")
        );
        return projectRepository.save(project);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<?> delete(@PathVariable String id, Authentication auth) {
        return projectRepository.findById(id)
            .filter(p -> p.getUserId().equals(auth.getName()))
            .map(p -> {
                projectRepository.delete(p);
                return ResponseEntity.ok(Map.of("deleted", true));
            })
            .orElse(ResponseEntity.notFound().build());
    }
}
