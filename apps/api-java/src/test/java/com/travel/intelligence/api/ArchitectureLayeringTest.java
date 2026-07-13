package com.travel.intelligence.api;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

class ArchitectureLayeringTest {

    private static final Path MAIN_JAVA = Path.of("src/main/java");
    private static final Pattern OLD_PACKAGE_DECLARATION = Pattern.compile(
            "^package com\\.travel\\.intelligence\\.api\\.(client|config|session|web|tool\\.mcp|tool);\\s*$");
    private static final Pattern FORBIDDEN_DOMAIN_IMPORT = Pattern.compile(
            "^import (org\\.springframework\\.(web|security)\\..*|org\\.springframework\\.data\\..*|.*\\.(RestClient|WebClient|.*Repository|.*Controller));\\s*$");
    private static final Pattern CONSOLIDATION_DOMAIN_IMPORT = Pattern.compile(
            "^import (jakarta\\.persistence\\..*|org\\.springframework\\..*|com\\.fasterxml\\.jackson\\..*|.*\\.(RestClient|WebClient|.*Repository|.*Controller));\\s*$");
    private static final Pattern CONSOLIDATION_APPLICATION_IMPORT = Pattern.compile(
            "^import (com\\.travel\\.intelligence\\.api\\.(infrastructure\\..*|.*\\.infrastructure\\..*)|org\\.springframework\\.web\\..*|org\\.springframework\\.http\\.HttpStatus|org\\.springframework\\.security\\.core\\.Authentication|org\\.springframework\\.data\\..*|.*\\.(RestClient|WebClient|HttpHeaders|JpaRepository));\\s*$");
    private static final Pattern CONSOLIDATION_WEB_IMPORT = Pattern.compile(
            "^import (com\\.travel\\.intelligence\\.api\\..*\\.infrastructure\\..*|.*\\.(JpaRepository|.*Repository));\\s*$");
    private static final SourceLayout SOURCE_LAYOUT = loadSourceLayout();
    private static final Set<String> ALLOWED_DOMAIN_CONSOLIDATION_VIOLATIONS = Set.of();
    private static final Set<String> ALLOWED_APPLICATION_CONSOLIDATION_VIOLATIONS = Set.of();

    @Test
    void activeSourcesDoNotUseRetiredPackages() throws IOException {
        List<String> violations = new ArrayList<>();
        for (Path file : SOURCE_LAYOUT.all()) {
            List<String> lines = Files.readAllLines(file);
            for (int i = 0; i < lines.size(); i++) {
                if (OLD_PACKAGE_DECLARATION.matcher(lines.get(i)).matches()) {
                    violations.add(relative(file) + ":" + (i + 1) + " uses retired package declaration");
                }
            }
        }

        assertTrue(violations.isEmpty(), () -> String.join(System.lineSeparator(), violations));
    }

    @Test
    void domainSourcesDoNotDependOnWebSecurityRepositoriesOrHttpClients() throws IOException {
        List<String> violations = new ArrayList<>();
        for (Path file : SOURCE_LAYOUT.domain()) {
            List<String> lines = Files.readAllLines(file);
            for (int i = 0; i < lines.size(); i++) {
                if (FORBIDDEN_DOMAIN_IMPORT.matcher(lines.get(i)).matches()) {
                    violations.add(relative(file) + ":" + (i + 1) + " imports forbidden domain dependency: " + lines.get(i));
                }
            }
        }

        assertTrue(violations.isEmpty(), () -> String.join(System.lineSeparator(), violations));
    }

    @Test
    void domainSourcesOnlyUseKnownConsolidationViolations() throws IOException {
        List<String> violations = collectImportViolations(SOURCE_LAYOUT.domain(), CONSOLIDATION_DOMAIN_IMPORT);
        List<String> unexpected = violations.stream()
                .filter(violation -> !ALLOWED_DOMAIN_CONSOLIDATION_VIOLATIONS.contains(violation))
                .toList();
        List<String> staleAllowlist = ALLOWED_DOMAIN_CONSOLIDATION_VIOLATIONS.stream()
                .filter(allowed -> !violations.contains(allowed))
                .sorted()
                .toList();

        assertTrue(unexpected.isEmpty(), () -> "Unexpected domain consolidation violations:%n%s".formatted(String.join(System.lineSeparator(), unexpected)));
        assertTrue(staleAllowlist.isEmpty(), () -> "Remove stale domain consolidation allowlist entries:%n%s".formatted(String.join(System.lineSeparator(), staleAllowlist)));
    }

    @Test
    void applicationSourcesOnlyUseKnownConsolidationViolations() throws IOException {
        List<String> violations = collectImportViolations(SOURCE_LAYOUT.application(), CONSOLIDATION_APPLICATION_IMPORT);
        List<String> unexpected = violations.stream()
                .filter(violation -> !ALLOWED_APPLICATION_CONSOLIDATION_VIOLATIONS.contains(violation))
                .toList();
        List<String> staleAllowlist = ALLOWED_APPLICATION_CONSOLIDATION_VIOLATIONS.stream()
                .filter(allowed -> !violations.contains(allowed))
                .sorted()
                .toList();

        assertTrue(unexpected.isEmpty(), () -> "Unexpected application consolidation violations:%n%s".formatted(String.join(System.lineSeparator(), unexpected)));
        assertTrue(staleAllowlist.isEmpty(), () -> "Remove stale application consolidation allowlist entries:%n%s".formatted(String.join(System.lineSeparator(), staleAllowlist)));
    }

    @Test
    void webSourcesDoNotImportPersistenceRepositoriesDirectly() throws IOException {
        List<String> violations = collectImportViolations(SOURCE_LAYOUT.web(), CONSOLIDATION_WEB_IMPORT);

        assertTrue(violations.isEmpty(), () -> "Unexpected web persistence imports:%n%s".formatted(String.join(System.lineSeparator(), violations)));
    }

    private static List<String> collectImportViolations(List<Path> files, Pattern forbiddenImport) throws IOException {
        List<String> violations = new ArrayList<>();
        for (Path file : files) {
            List<String> lines = Files.readAllLines(file);
            for (String line : lines) {
                if (forbiddenImport.matcher(line).matches()) {
                    violations.add(normalizedRelative(file) + "|" + line);
                }
            }
        }
        return violations;
    }

    private static List<Path> javaFiles(Path root) throws IOException {
        if (!Files.exists(root)) {
            return List.of();
        }
        try (Stream<Path> stream = Files.walk(root)) {
            return stream
                    .filter(Files::isRegularFile)
                    .filter(path -> path.toString().endsWith(".java"))
                    .toList();
        }
    }

    private static String relative(Path file) {
        return Path.of("").toAbsolutePath().relativize(file.toAbsolutePath()).toString();
    }

    private static String normalizedRelative(Path file) {
        return relative(file).replace('\\', '/');
    }

    private static SourceLayout loadSourceLayout() {
        try {
            List<Path> all = javaFiles(MAIN_JAVA);
            return new SourceLayout(
                    all,
                    bySegment(all, "domain"),
                    bySegment(all, "application"),
                    bySegment(all, "infrastructure"),
                    bySegment(all, "web"),
                    bySegment(all, "config"));
        } catch (IOException ex) {
            throw new IllegalStateException("Could not read Java source layout", ex);
        }
    }

    private static List<Path> bySegment(List<Path> files, String segment) {
        return files.stream()
                .filter(path -> path.toString().contains("\\" + segment + "\\") || path.toString().contains("/" + segment + "/"))
                .toList();
    }

    private record SourceLayout(
            List<Path> all,
            List<Path> domain,
            List<Path> application,
            List<Path> infrastructure,
            List<Path> web,
            List<Path> config) {
    }
}
